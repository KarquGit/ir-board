# iRacing SDK compatibility

iR-Board uses `pyirsdk==1.3.5`, a third-party Python wrapper for the iRacing SDK, not an official iRacing Python package. Live operation requires Windows and a running simulator. It does not use the account Data API or request iRacing credentials.

Telemetry is read from SDK shared memory. Each snapshot freezes and releases the variable buffer; absent variables remain unavailable. Session metadata comes from SDK session information. Driver flags use FlairID with a bundled numeric country lookup, with explicit country fields and FlairName as fallbacks; ClubName never determines nationality. The normalized clutch value is pedal depression (0 released, 1 pressed). Speed remains in m/s on the wire; display units and unit-bearing pit speed limits are converted separately. Live PlayerCarSL RPM thresholds take precedence over DriverInfo thresholds. The pit limiter indicator reads EngineWarnings bit 0x10; it does not toggle the limiter. Its speed-limit sign is hidden if the limit or limiter status is unavailable. Standings retain drivers without usable track coordinates, and same-class relative gaps use CarIdxEstTime when available. Derived gaps, fuel estimates and learned driving lines are estimates, not additional official telemetry channels.

Pit selections are sent using the wrapper's `pit_command`, which broadcasts the SDK Windows message. This is not a write to telemetry memory or simulated keyboard input. The following modes and units were checked against the pinned wrapper source:

| Mode | Meaning | Value |
| --- | --- | --- |
| 0 | Clear service selections | 0 |
| 1 | Windshield tear-off | 0 |
| 2 | Add fuel | Integer liters |
| 3, 4, 5, 6 | Replace LF, RF, LR, RR tire | Integer kPa; 0 retains pressure |
| 8 | Fast repair | 0 |

The compound selector additionally broadcasts numeric mode 12. The pinned wrapper transports this value but its named constants stop at mode 11. Compound support therefore requires verification against the installed simulator SDK and the selected car; it is not established by the wrapper constants. Choices use `DriverInfo.DriverTires` entries (`TireIndex` and `TireCompoundType`), rather than assuming index meanings. If metadata is absent, the selector is disabled. An unsupported selection may be ignored.

Readback uses `PitSvFlags`, `PitSvFuel`, tire pressures and `PitSvStatus` (with a legacy status-name fallback). These describe requested services/status, not proof that every submitted setting was accepted. The driver must be in the car; replay and disconnected operation cannot send commands. Remote control additionally requires pairing or an explicit access token. Demo mode sends nothing.

Requests are validated before dispatch and serialized on the SDK-owning thread. A changed session cancels queued work. A timeout or partial failure requires inspecting the in-game black box before retrying. There is no automatic retry or atomic SDK transaction.

## Widget data and derived values

| Widget | Data and behavior |
| --- | --- |
| Standings / Relative | Overall and class positions, grid changes in races, country, team, class, iRating, license, detailed last/best/recent average lap, gaps and intervals in Standings. Standings timing and optional car/lap/stint/rating fields have separate columns. Relative shows its main time difference without secondary timing rows. GAP is green when the comparable gap to the class leader falls, red when it rises, and neutral after missing data, PIT transitions or a reference change. Red marks a car lapping the focused driver; blue marks a lapped car, accounting for the start/finish boundary. Both tables follow the focused row; manual scrolling pauses following for 15 seconds. |
| Race status | Observed PIT lane and stationary durations, last observed stop, out-lap, stint, compound index/name, radio and per-car penalties/results. Missing track position alone never means retirement. Names of compounds are shared only between matching car models. |
| Speed / RPM | Live shift thresholds, speed units, temperatures, available pressures and voltage, warnings, DRS/P2P and limiter state. Unsupported values remain unavailable. |
| Driving inputs | Processed pedals, gear, speed and a recent input trace. Active ABS turns the brake bar orange with fast blinking. Clutch values represent pedal depression. |
| Lap timing | Valid SDK delta references, predicted lap, observed clean lap history and a locally saved clean personal best per car/track. |
| Fuel | Clean-lap samples, min/max/average usage, estimated laps/time, capacity, instantaneous kg/h and refuel calculation. Global checkered state alone does not mark the player's race finished. |
| Car adjustments | Available numeric SDK dc controls, including signed settings. Unsupported controls remain unavailable. |
| Spotter | SDK left/right occupancy, including two cars on either side; absent/off data is distinct from clear. |
| PIT | Explicit validated requests and SDK service readback; compound selection must match current car metadata. |
| SDK inspector | Available telemetry fields, arrays and session metadata; non-finite numbers are normalized before JSON transport. |

Class SOF and provisional iRating changes are calculated locally. The latter is an estimate, not an official result. Gaps fall back to distance/lap-time estimates when timing is unavailable. PIT durations and recent lap statistics require observation: joining mid-stop cannot recover its start time. In spectator mode race tables follow the camera car when located; PIT writes remain disabled. Learned maps use SDK GPS when available and otherwise integrate SDK yaw and forward/lateral velocity over a full continuous lap. Motion-derived maps are approximate, require valid heading and velocity samples, and are stored locally with their source identified. The last saved line remains visible during background recording. Each full clean lap replaces it; changed incident counts, off-track/PIT samples and discontinuities discard the new attempt without removing the saved map. Map marker fill uses the SDK class color where available, with deterministic fallbacks. Known classes have distinct marker shapes; player and PIT outlines remain independent of class color. No external circuit geometry is used.

Automated race tests cover lap-boundary comparisons, PIT transitions, session resets, missing values, car changes, country lookup, control safety and browser rendering. Validate multiclass races, lapping across the line, camera changes, PIT entry/stall/exit, raw pedals and unsupported controls in the simulator as well.

## Live simulator checks

Automated tests validate encoding, units, rejection paths, queue ownership and HTTP authorization using test doubles. They do not establish simulator acceptance. On Windows, use a practice session to compare the in-game pit black box with each wheel selection, retained/changed pressure, fuel amount, windshield and fast repair. Check readback after applying and after an actual pit stop. Verify compound indices separately on a suitable car, then test disconnect/reconnect and car/session changes. Never perform initial validation during a competitive session.

This is a technical interoperability review, not a certification by iRacing or a legal assessment of its current SDK agreement.
