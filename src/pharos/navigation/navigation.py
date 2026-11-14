"""Navigation state over validated local-metre geometry."""

from dataclasses import dataclass
import math

from .routes import FixtureRouteProvider, validate_route


@dataclass(frozen=True)
class Fix:
    timestamp: float
    x: float
    y: float
    accuracy: float


@dataclass(frozen=True)
class Thresholds:
    max_age: float = 5
    max_accuracy: float = 12
    turn_radius: float = 6
    detour_distance: float = 18
    detour_duration: float = 3
    arrival_radius: float = 6
    corridor: float = 8
    approach_window: float = 12
    max_corner_skip: float = 25
    reroute_cooldown: float = 30

    def __post_init__(self):
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError('Navigation thresholds must be positive finite numbers.')
        if self.corridor > self.detour_distance:
            raise ValueError('Route corridor cannot exceed detour distance.')


def distance(point, other):
    return math.hypot(point[0] - other[0], point[1] - other[1])


def along_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    return ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / distance(start, end)


def segment_distance(point, start, end):
    length = distance(start, end)
    if not length:
        return distance(point, start)
    fraction = max(0, min(1, along_segment(point, start, end) / length))
    return distance(point, (start[0] + fraction * (end[0] - start[0]), start[1] + fraction * (end[1] - start[1])))


class Navigation:
    def __init__(self, route=None, thresholds=None, *, live=False):
        self.live = live
        self.route = validate_route(route, allow_live=live) if route is not None else FixtureRouteProvider().get_route('du-bois-library')
        self.thresholds = thresholds or Thresholds()
        self.active = False
        self.paused = False
        self.step = 0
        self.event_index = 0
        self.last_timestamp = None
        self.last_now = None
        self.previous_point = None
        self.weak = False
        self.off_since = None
        self.detour_announced = False
        self.missed_announced = False
        self.last_reroute = -math.inf
        self.arrival_count = 0
        self.last_cue = None

    def cue(self, status, text, *, announce=True, **data):
        text = text if self.live else 'Simulation: ' + text
        result = dict(status=status, text=text, speech=text if announce else '', priority=2,
                      data=dict(simulated=not self.live, step=self.step, active=self.active, paused=self.paused, **data))
        if announce:
            self.last_cue = result
        return result

    def start(self):
        self.__init__(self.route, self.thresholds, live=self.live)
        if self.live:
            self.active = True
            return self.cue('route_started', f"Route {self.route['name']} started. Waiting for a fresh location fix.")
        self.active = True
        return self.cue('route_started', f"starting {self.route['name']} using invented route geometry. "
                        + self.route['instructions'][0] + ' Use next to advance the replay.')

    def stop(self):
        self.active = self.paused = False
        self.last_cue = None
        self.previous_point = None
        self.arrival_count = 0

    def pause(self):
        if not self.active:
            return self.cue('route_inactive', 'no route is running.', announce=False)
        self.paused = True
        self.previous_point = None
        self.off_since = None
        self.arrival_count = 0
        return self.cue('route_paused', 'route paused. Location updates will not advance until resume.')

    def resume(self):
        if not self.active:
            return self.cue('route_inactive', 'no route is running.', announce=False)
        self.paused = False
        self.previous_point = None
        self.arrival_count = 0
        return self.cue('route_resumed', 'Route resumed. Waiting for a fresh accurate fix.' if self.live else
                        'route resumed; waiting for a fresh accurate fix. ' + self.route['instructions'][self.step])

    def weak_signal(self, text='location signal is weak. Route progress is paused.'):
        announce = not self.weak
        self.weak = True
        self.arrival_count = 0
        self.off_since = None
        self.previous_point = None
        return self.cue('weak_signal', text, announce=announce)

    def tick(self, now):
        if not self.active or self.paused:
            return self.cue('route_paused' if self.paused else 'route_inactive', 'route is paused or inactive.', announce=False)
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
            return self.cue('invalid_fix', 'invalid clock update ignored.', announce=False)
        if self.last_now is not None and now < self.last_now:
            return self.cue('ignored_fix', 'out-of-order clock update ignored.', announce=False)
        self.last_now = now
        if self.last_timestamp is None or now - self.last_timestamp > self.thresholds.max_age:
            return self.weak_signal()
        return self.cue('progress', self.route['instructions'][self.step], announce=False)

    def _advance(self, point, reason):
        self.step += 1
        self.previous_point = point
        self.off_since = None
        self.detour_announced = self.missed_announced = False
        return self.cue('turn', self.route['instructions'][self.step], advance_reason=reason)

    def update(self, fix, now):
        if not self.active:
            return self.cue('route_inactive', 'no route is running.', announce=False)
        if self.paused:
            return self.cue('route_paused', 'route is paused.', announce=False)
        values = (fix.timestamp, fix.x, fix.y, fix.accuracy, now)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values) or now < 0 or fix.timestamp < 0:
            self.arrival_count = 0
            self.previous_point = None
            self.off_since = None
            return self.cue('invalid_fix', 'invalid location update; progress paused.', announce=False)
        if self.last_now is not None and now < self.last_now:
            return self.cue('ignored_fix', 'out-of-order clock update ignored.', announce=False)
        self.last_now = now
        limits = self.thresholds
        if now - fix.timestamp > limits.max_age or fix.timestamp > now or not 0 <= fix.accuracy <= limits.max_accuracy:
            return self.weak_signal()
        if self.last_timestamp is not None and fix.timestamp <= self.last_timestamp:
            return self.cue('ignored_fix', 'duplicate or out-of-order location ignored.', announce=False)
        if self.last_timestamp is not None and fix.timestamp - self.last_timestamp > limits.max_age:
            self.arrival_count = 0
            self.previous_point = None
            self.off_since = None
        self.last_timestamp = fix.timestamp
        recovered, self.weak = self.weak, False
        point, points = (fix.x, fix.y), self.route['points']
        start, end = points[self.step:self.step + 2]
        final_step = self.step == len(points) - 2
        along = along_segment(point, start, end)
        if not final_step:
            if distance(point, end) <= limits.turn_radius and (
                not self.live or (
                    self.previous_point is not None
                    and distance(self.previous_point, end) <= limits.turn_radius
                    and segment_distance(self.previous_point, start, end) <= limits.corridor
                    and fix.accuracy <= limits.turn_radius
                )
            ):
                return self._advance(point, 'near_corner')
            next_end = points[self.step + 2]
            previous = self.previous_point
            passed_corner = (previous is not None and
                             segment_distance(previous, start, end) <= limits.corridor and
                             distance(start, end) - limits.approach_window <= along_segment(previous, start, end) <= distance(start, end) + limits.turn_radius and
                             along >= distance(start, end) - limits.turn_radius and
                             segment_distance(point, end, next_end) <= limits.corridor and
                             limits.turn_radius < along_segment(point, end, next_end) <= limits.max_corner_skip)
            if passed_corner and (not self.live or fix.accuracy <= limits.turn_radius):
                return self._advance(point, 'passed_corner_between_fixes')
            if along > distance(start, end) + limits.turn_radius and segment_distance(point, end, next_end) > limits.corridor and not self.missed_announced:
                self.missed_announced = True
                self.previous_point = None
                self.off_since = now
                return self.cue('missed_turn', 'possible missed turn. Progress paused; return to the checked route.')
        if segment_distance(point, start, end) > (limits.corridor if self.live else limits.detour_distance):
            self.arrival_count = 0
            self.previous_point = None
            if self.off_since is None:
                self.off_since = now
            if now - self.off_since >= limits.detour_duration and not self.detour_announced:
                self.detour_announced = True
                due = now - self.last_reroute >= limits.reroute_cooldown
                if due:
                    self.last_reroute = now
                return self.cue('detour', 'sustained detour detected. Live rerouting is unavailable; replay must return to the checked route.', reroute_due=due)
            return self.cue('off_route', 'off the route; progress paused.', announce=False)
        self.previous_point = point
        self.off_since = None
        self.detour_announced = False
        if final_step and distance(point, points[-1]) <= limits.arrival_radius:
            if fix.accuracy > limits.arrival_radius:
                return self.weak_signal('location is too imprecise to confirm arrival. Progress paused.')
            self.arrival_count += 1
            if self.arrival_count >= 2:
                self.active = False
                return self.cue('arrived', 'arrived in the destination area. This does not identify an entrance or door.')
            return self.cue('near_destination', 'near the destination area; waiting for another accurate fix.')
        self.arrival_count = 0
        if self.live and (recovered or self.last_cue['status'] in {'route_started', 'route_resumed', 'missed_turn', 'detour'}):
            return self.cue('guidance', self.route['instructions'][self.step])
        if recovered:
            return self.cue('signal_recovered', 'location signal recovered. ' + self.route['instructions'][self.step])
        return self.cue('progress', self.route['instructions'][self.step], announce=False)

    def next_event(self):
        if self.live:
            return self.cue('live_route', 'Live routes only accept phone fixes.', announce=False)
        if not self.active or self.paused:
            return self.cue('route_paused' if self.paused else 'route_inactive', 'route is paused or inactive.', announce=False)
        events = self.route['events']
        if self.event_index >= len(events):
            self.active = False
            return self.cue('replay_finished', 'replay exhausted without confirmed arrival.')
        event = events[self.event_index]
        self.event_index += 1
        result = self.update(Fix(**event['fix']), event['now']) if event.get('fix') is not None else self.tick(event['now'])
        result['data']['event'] = event['label']
        result['data']['event_index'] = self.event_index
        return result
