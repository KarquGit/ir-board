"""Validated pit-service requests. SDK broadcasts do not acknowledge game acceptance."""
import math

TIRES = {'lf': 3, 'rf': 4, 'lr': 5, 'rr': 6}

def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name}: required {low}–{high} (integer)')
    return value

def commands(plan):
    if not isinstance(plan, dict) or set(plan) - {'tires', 'fuel', 'windshield', 'fast_repair', 'compound'}:
        raise ValueError('Invalid pit-service plan')
    tires = plan.get('tires', {})
    if not isinstance(tires, dict) or set(tires) - set(TIRES):
        raise ValueError('Invalid tire selection')
    result = [(0, 0)]  # This form replaces all checkboxes, never appends implicitly.
    for tire, pressure in tires.items():
        pressure = integer(pressure, 'Pressure in kPa (0 = retain)', 0, 500)
        if pressure and pressure < 70:
            raise ValueError('Pressure: 70–500 kPa, or 0 to retain')
        result.append((TIRES[tire], pressure))
    fuel = integer(plan.get('fuel', 0), 'Fuel in liters', 0, 500)
    if fuel:
        result.append((2, fuel))
    for name, command in [('windshield', 1), ('fast_repair', 8)]:
        enabled = plan.get(name, False)
        if type(enabled) is not bool:
            raise ValueError('Service selection must be a boolean')
        if enabled:
            result.append((command, 0))
    compound = plan.get('compound')
    if compound is not None:
        result.append((12, integer(compound, 'Compound index', 0, 9)))
    return result


def read_pit(get, driver_info, on_track):
    flags = get('PitSvFlags')
    available = flags is not None
    return dict(available=available, can_control=available and on_track and not bool(get('IsReplayPlaying', False)),
                flags=flags, fuel=get('PitSvFuel'), compound=get('PitSvTireCompound'),
                compounds=read_compounds(driver_info),
                pressures={t: get(k) for t,k in [('lf','PitSvLFP'),('rf','PitSvRFP'),('lr','PitSvLRP'),('rr','PitSvRRP')]},
                status=get('PitSvStatus', get('PlayerCarPitSvStatus')), fast_repairs=get('FastRepairAvailable'),
                fuel_max=fuel_capacity(driver_info))


def fuel_capacity(info):
    capacity, fraction = info.get('DriverCarFuelMaxLtr'), info.get('DriverCarMaxFuelPct', 1)
    if isinstance(capacity, (int, float)) and math.isfinite(capacity) and capacity > 0:
        if isinstance(fraction, (int, float)) and math.isfinite(fraction) and 0 < fraction <= 1:
            return capacity * fraction
        return capacity
    return None


def validate_compound(batch,pit):
    choices={c.get('index') for c in (pit.get('compounds') or []) if isinstance(c,dict)}
    if any(mode==12 and value not in choices for mode,value in batch):
        raise ValueError('Selected tire compound is unavailable for the current car.')


def read_compounds(driver_info):
    """Use simulator-provided names and indices; never assume Dry=0 or Wet=1."""
    tires = driver_info.get('DriverTires', [])
    if not isinstance(tires, list):
        return []
    result = {}
    for tire in tires:
        if not isinstance(tire, dict):
            continue
        index = tire.get('TireIndex')
        name = tire.get('TireCompoundType') or tire.get('CompoundType')
        if type(index) is int and 0 <= index <= 9 and isinstance(name, str) and name.strip():
            result[index] = dict(index=index, name=name.strip()[:60])
    return [result[index] for index in sorted(result)]
