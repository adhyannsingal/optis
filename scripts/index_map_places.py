"""Index mapped names and numbered addresses from the same OSM extract as Valhalla."""

import argparse
import sqlite3
import statistics
from pathlib import Path

import osmium


class Places(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = set()

    def add(self, tags, lat, lon):
        city = tags.get("addr:city")
        name = tags.get("name")
        if name:
            self.rows.add((f"{name}, {city}" if city else name, round(lat, 6), round(lon, 6)))
        street, number = tags.get("addr:street"), tags.get("addr:housenumber")
        if street and number:
            address = f"{number} {street}"
            self.rows.add((f"{address}, {city}" if city else address, round(lat, 6), round(lon, 6)))

    def node(self, node):
        if node.location.valid():
            self.add(node.tags, node.location.lat, node.location.lon)

    def way(self, way):
        if not (way.tags.get("name") or way.tags.get("addr:housenumber")):
            return
        points = [(node.lat, node.lon) for node in way.nodes if node.location.valid()]
        if points:
            self.add(way.tags, statistics.mean(p[0] for p in points), statistics.mean(p[1] for p in points))


    def area(self, area):
        if area.from_way() or not (area.tags.get("name") or area.tags.get("addr:housenumber")):
            return
        points = [(node.lat, node.lon) for ring in area.outer_rings() for node in ring if node.location.valid()]
        if points:
            self.add(area.tags, statistics.mean(p[0] for p in points), statistics.mean(p[1] for p in points))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extract", type=Path)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    places = Places()
    places.apply_file(str(options.extract), locations=True, idx="flex_mem")
    pending = options.output.with_suffix(options.output.suffix + ".building")
    pending.unlink(missing_ok=True)
    database = sqlite3.connect(pending)
    try:
        with database:
            database.execute("CREATE VIRTUAL TABLE places USING fts5(name, lat UNINDEXED, lon UNINDEXED)")
            database.executemany("INSERT INTO places VALUES (?, ?, ?)", sorted(places.rows))
    finally:
        database.close()
    pending.replace(options.output)
    print(f"Indexed {len(places.rows)} mapped destinations.")
