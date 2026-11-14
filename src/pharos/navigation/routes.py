"""Validated route-provider boundary; only synthetic local-metre routes are enabled."""

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Protocol

DEFAULT_ROUTE = Path(__file__).with_name('fixtures') / 'library_walk.json'


class RouteError(ValueError):
    pass


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_route(document, *, allow_live=False):
    if not isinstance(document, dict) or type(document.get('simulated')) is not bool:
        raise RouteError('Route must declare whether it is simulated.')
    if not document['simulated'] and (not allow_live or document.get('events')):
        raise RouteError('Live routes require a checked route file and cannot contain replay events.')
    if document.get('coordinate_system', 'local_metres') != 'local_metres':
        raise RouteError('Route geometry must use local metres.')
    if not isinstance(document.get('name'), str) or not document['name'].strip():
        raise RouteError('Route needs a name.')
    points, instructions, events = document.get('points'), document.get('instructions'), document.get('events', [])
    if not isinstance(points, list) or len(points) < 2 or any(not isinstance(p, list) or len(p) != 2 or not all(number(v) for v in p) for p in points):
        raise RouteError('Route needs at least two finite coordinate pairs.')
    if any(math.dist(a, b) < .001 for a, b in zip(points, points[1:])):
        raise RouteError('Consecutive route points must differ.')
    if not isinstance(instructions, list) or len(instructions) != len(points) - 1 or any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in instructions):
        raise RouteError('Each segment needs a nonempty instruction.')
    if not isinstance(events, list):
        raise RouteError('Replay events must be a list.')
    previous = -1
    for event in events:
        if not isinstance(event, dict) or not number(event.get('now')) or event['now'] < previous or event['now'] < 0:
            raise RouteError('Replay clock must be finite, nonnegative and ordered.')
        if not isinstance(event.get('label'), str):
            raise RouteError('Replay events need labels.')
        fix = event.get('fix')
        if fix is not None and (not isinstance(fix, dict) or set(fix) != {'timestamp', 'x', 'y', 'accuracy'} or not all(number(value) for value in fix.values())):
            raise RouteError('Replay fix fields are invalid.')
        previous = event['now']
    result = deepcopy(document)
    result.setdefault('events', [])
    return result


class RouteProvider(Protocol):
    def get_route(self, destination_id: str, template: dict | None = None) -> dict: ...


class FixtureRouteProvider:
    def __init__(self, path=DEFAULT_ROUTE):
        self.path = Path(path)

    def get_route(self, destination_id, template=None):
        if destination_id != 'du-bois-library':
            raise RouteError('No simulated route for that saved destination.')
        try:
            return validate_route(json.loads(self.path.read_text()))
        except (OSError, ValueError) as error:
            raise RouteError(f'Simulated route unavailable: {error}') from error
