import fs from 'node:fs';
import assert from 'node:assert/strict';
import {parseCSV, shortestRoute} from '../web/tram/router.mjs';

const root = new URL('../', import.meta.url);
const graph = JSON.parse(fs.readFileSync(new URL('data/tram_edges.json', root)));
const stations = parseCSV(fs.readFileSync(new URL('data/tram_stations_estimated.csv', root), 'utf8'));
assert.equal(stations.length, 45);
const ids = stations.map(r => r.station_no);
const all = graph.nodes.map(n => n.id);
const index = new Map(all.map((id, i) => [id, i]));
const distance = all.map((a, i) => all.map((b, j) => i === j ? 0 : Infinity));
for (const arc of graph.routing_arcs) {
  distance[index.get(arc.from_id)][index.get(arc.to_id)] = ids.includes(arc.to_id) ? 1 : 0;
}
// Independent all-pairs Floyd–Warshall oracle, including zero-cost junction entries.
for (let k = 0; k < all.length; k++)
  for (let i = 0; i < all.length; i++)
    for (let j = 0; j < all.length; j++)
      distance[i][j] = Math.min(distance[i][j], distance[i][k] + distance[k][j]);
let tested = 0;
for (const a of ids) for (const b of ids) {
  const route = shortestRoute(graph, a, b);
  assert.equal(route.stops, distance[index.get(a)][index.get(b)]);
  assert.equal(route.stationIds.length, route.stops + 1);
  assert.equal(route.nodeIds[0], a);
  assert.equal(route.nodeIds.at(-1), b);
  for (let i = 0; i < route.edgeIds.length; i++) {
    const edge = graph.edges.find(e => e.id === route.edgeIds[i]);
    assert.ok((edge.from_id === route.nodeIds[i] && edge.to_id === route.nodeIds[i + 1] && edge.forward_allowed)
      || (edge.to_id === route.nodeIds[i] && edge.from_id === route.nodeIds[i + 1] && edge.reverse_allowed));
  }
  tested++;
}
assert.deepEqual(shortestRoute(graph, '240', '202').stationIds, ['240', '201', '202']);
assert.deepEqual(shortestRoute(graph, '212', '241').stationIds, ['212', '241']);
assert.equal(shortestRoute(graph, '218', '218').stops, 0);
assert.ok(shortestRoute(graph, '244', '245').stationIds.includes('233'));
assert.deepEqual(parseCSV('a,b\r\n1,"x,y"\r\n'), [{a:'1', b:'x,y'}]);
assert.deepEqual(parseCSV('a,b\n1,"x""y\nz"'), [{a:'1', b:'x"y\nz'}]);
const disconnected = {...graph, edges: []};
assert.equal(shortestRoute(disconnected, '211', '218'), null);
console.log(`PASS: ${tested} station pairs; loop, branches, junction cost, same station, disconnected graph, CSV quoting.`);
