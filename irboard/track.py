"""Learn a local driving line from SDK GPS or motion, never from circuit assets."""
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

EARTH = 6371000
SAMPLES = 600


def data_directory():
    override=os.environ.get('IRBOARD_DATA_DIR')
    if override:return Path(override)
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'iR-Board'
    base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    current=base/'iR-Board'
    legacy=base/('iR-'+'BOARD')
    return legacy if legacy.exists() and not current.exists() else current


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


class MapStore:
    def __init__(self,directory=None):self.directory=Path(directory) if directory else data_directory()/'tracks'
    def path(self,key):return self.directory/(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()+'.json')
    def load(self,key):
        try:
            path=self.path(key)
            if path.stat().st_size>200000:return None
            value=json.loads(path.read_text(encoding='utf-8'))
            pts=value.get('points',[])
            if value.get('source') not in ('sdk-gps','sdk-motion') or value.get('format')!=1 or value.get('track')!=list(key) or len(pts)!=SAMPLES:return None
            if any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) and abs(v)<200000 for v in p) for p in pts):return None
            if max(max(p[i] for p in pts)-min(p[i] for p in pts) for i in (0,1))<40:return None
            return value
        except (OSError,ValueError,TypeError,AttributeError):return None
    def save(self,key,points,source='sdk-gps'):
        value=dict(format=1,source=source,track=list(key),points=points)
        self.directory.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.directory,delete=False) as file:
                temporary=Path(file.name);json.dump(value,file,allow_nan=False,separators=(',',':'))
            os.replace(temporary,self.path(key))
        finally:
            if temporary and temporary.exists():temporary.unlink()
        return value


class TrackRecorder:
    def __init__(self,store=None):
        self.store=store or MapStore()
        self.key=None;self.learned=None;self.origin=None;self.mode=None
        self.reset_attempt()
    def reset_attempt(self):
        self.previous=None;self.samples=[];self.recording=False;self.progress=0
        self.motion_previous=None;self.motion_xy=(0.,0.)
        self.incidents=None
    def snapshot(self,message=None):
        source=self.learned['source'] if self.learned else self.mode or 'sdk-gps'
        return dict(source=source,status='ready' if self.learned else 'learning' if self.recording else 'waiting',
                    progress=1 if self.learned else self.progress,points=self.learned['points'] if self.learned else [],
                    updating=bool(self.learned and self.recording),update_progress=self.progress,
                    message=message or (('Approximate driving line from SDK motion telemetry' if source=='sdk-motion' else 'Local SDK GPS driving line') if self.learned else 'Cross start/finish, then drive one complete on-track lap to learn this layout.'))
    def update(self,key,car,now):
        if key!=self.key:
            self.key=key;self.learned=self.store.load(key);self.origin=None;self.mode=None;self.reset_attempt()
        lat,lon,pct=car.get('lat'),car.get('lon'),car.get('lap_pct')
        eligible=car.get('on_track') and not car.get('pit') and not car.get('garage') and not car.get('replay') and car.get('surface',3) in (None,3) and not (car.get('session_flags',0) or 0) & 0xC118
        incidents=car.get('incidents')
        if finite(incidents) and finite(self.incidents) and incidents!=self.incidents:
            self.reset_attempt()
            return self.snapshot('Lap had an incident; the saved map is retained. Waiting for the next clean lap.' if self.learned else 'Lap had an incident. Cross start/finish and drive a clean lap.')
        self.incidents=incidents
        gps=all(finite(v) for v in (lat,lon)) and -90<lat<90 and -180<=lon<=180 and (lat!=0 or lon!=0)
        yaw,vx,vy=car.get('yaw'),car.get('velocity_x'),car.get('velocity_y')
        motion=all(finite(v) for v in (yaw,vx,vy)) and math.hypot(vx,vy)<200
        if not eligible or not all(finite(v) for v in (pct,now)) or not 0<=pct<1 or not (gps or motion):
            self.reset_attempt();return self.snapshot('Waiting for on-track GPS or heading and velocity telemetry. Enter the car and drive a complete lap.')
        mode='sdk-gps' if gps else 'sdk-motion'
        if mode!=self.mode:
            self.reset_attempt();self.mode=mode
            self.incidents=incidents
        if gps:
            if self.origin is None:self.origin=(lat,lon)
            lat0,lon0=self.origin
            xy=((lon-lon0)*math.pi/180*EARTH*math.cos(math.radians(lat0)),-(lat-lat0)*math.pi/180*EARTH)
        else:
            # SDK velocities are in car axes (forward/left); yaw rotates them
            # into a fixed horizontal frame. Integrate observed samples only.
            velocity=(vx*math.cos(yaw)-vy*math.sin(yaw),-(vx*math.sin(yaw)+vy*math.cos(yaw)))
            if self.motion_previous is not None:
                t,old_velocity=self.motion_previous
                dt=now-t
                if dt<0 or dt>2:
                    self.reset_attempt()
                elif dt>0:
                    self.motion_xy=tuple(self.motion_xy[i]+(old_velocity[i]+velocity[i])*.5*dt for i in (0,1))
            self.motion_previous=(now,velocity)
            xy=self.motion_xy
        previous=self.previous;self.previous=(pct,xy,now)
        if previous is None:
            if pct <= .002:
                self.samples=[[0,*xy]];self.recording=True;self.progress=pct
            return self.snapshot()
        old,oldxy,oldtime=previous;dt=now-oldtime
        if dt==0:
            self.previous=previous
            return self.snapshot()
        # SDK lap progress can jitter backwards while stopped or near the line.
        # Ignore tiny reversals rather than interpreting them as an almost-full lap.
        if -.002 < pct-old < 0:
            self.previous=previous
            return self.snapshot()
        delta=(pct-old)%1
        distance=math.hypot(xy[0]-oldxy[0],xy[1]-oldxy[1])
        if dt<0 or dt>2 or delta>.035 or distance>max(80,(car.get('speed') or 0)*dt*3+15):
            self.reset_attempt()
            return self.snapshot('Lap recording restarted after a discontinuity. Drive a continuous lap.')
        wrapped=old>.9 and pct<.1
        if wrapped:
            save_error=False
            fraction=(1-old)/(delta or 1)
            crossing=[oldxy[i]+fraction*(xy[i]-oldxy[i]) for i in (0,1)]
            if self.recording and len(self.samples)>=40 and self.samples[-1][0]>.965:
                closure=math.hypot(crossing[0]-self.samples[0][1],crossing[1]-self.samples[0][2])
                if closure<60:
                    points=self._finish(crossing)
                    if points:
                        self.learned=dict(format=1,source=self.mode,track=list(key),points=points)
                        try:self.store.save(key,points,self.mode)
                        except OSError:save_error=True
            self.samples=[[0,*crossing]];self.recording=True
        if self.recording and (not self.samples or pct>self.samples[-1][0]+.0008):
            self.samples.append([pct,*xy]);self.progress=pct
        if wrapped and save_error:
            return self.snapshot('Telemetry map is ready in memory; it could not be saved to disk.')
        return self.snapshot()
    def _finish(self,crossing):
        samples=self.samples+[[1,*crossing]]
        if any(b[0]-a[0]>.035 for a,b in zip(samples,samples[1:])):return None
        if self.mode=='sdk-motion':
            # Remove small accumulated integration drift over the completed lap.
            drift=[crossing[i]-samples[0][i+1] for i in (0,1)]
            samples=[[p[0],p[1]-drift[0]*p[0],p[2]-drift[1]*p[0]] for p in samples]
        xs=[p[1] for p in samples];ys=[p[2] for p in samples]
        if max(max(xs)-min(xs),max(ys)-min(ys))<40:return None
        positions=[p[0] for p in samples];points=[]
        for i in range(SAMPLES):
            pct=i/SAMPLES;index=min(len(samples)-2,max(0,bisect.bisect_right(positions,pct)-1))
            a,b=samples[index:index+2];mix=(pct-a[0])/(b[0]-a[0] or 1)
            points.append([round(a[j]+mix*(b[j]-a[j]),3) for j in (1,2)])
        return points
