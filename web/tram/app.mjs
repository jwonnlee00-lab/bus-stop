import {parseCSV, shortestRoute} from './router.mjs';

const $ = id => document.getElementById(id);
const svg = $('map');
const ns = 'http://www.w3.org/2000/svg';
function element(tag, attrs, parent = svg, text) {
  const node = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  parent.append(node); return node;
}
async function load(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response;
}
try {
  const [csvResponse, graphResponse] = await Promise.all([
    load('../../data/tram_stations_estimated.csv'), load('../../data/tram_edges.json')]);
  const stations = parseCSV(await csvResponse.text());
  const graph = await graphResponse.json();
  if (stations.length !== 45) throw new Error('정거장 45개를 읽지 못했습니다.');
  // Station positions and names come from the unchanged CSV; junctions from JSON.
  const stationById = new Map(stations.map(s => [s.station_no, s]));
  const nodes = new Map(graph.nodes.map(n => [n.id, {...n, ...(stationById.has(n.id) ? {
    latitude: Number(stationById.get(n.id).latitude), longitude: Number(stationById.get(n.id).longitude),
    name: stationById.get(n.id).station_name} : {})}]));
  if (stations.some(s => !nodes.has(s.station_no))) throw new Error('좌표와 연결 데이터의 정거장 번호가 다릅니다.');
  const points = [...nodes.values()];
  const minLon = Math.min(...points.map(n => n.longitude)) - .008;
  const maxLon = Math.max(...points.map(n => n.longitude)) + .008;
  const minLat = Math.min(...points.map(n => n.latitude)) - .006;
  const maxLat = Math.max(...points.map(n => n.latitude)) + .006;
  const cos = Math.cos(36.35 * Math.PI / 180);
  const scale = Math.min(800 / ((maxLon - minLon) * cos), 670 / (maxLat - minLat));
  const xOffset = (900 - (maxLon - minLon) * cos * scale) / 2;
  const yOffset = (760 - (maxLat - minLat) * scale) / 2;
  const xy = n => [xOffset + (n.longitude - minLon) * cos * scale, yOffset + (maxLat - n.latitude) * scale];
  for (let lat = Math.ceil(minLat * 100) / 100; lat < maxLat; lat += .02) {
    const y = xy({latitude:lat, longitude:minLon})[1];
    element('line', {x1:30, x2:870, y1:y, y2:y, class:'grid'});
    element('text', {x:32, y:y - 5}, svg, `${lat.toFixed(2)}°N`);
  }
  for (let lon = Math.ceil(minLon * 100) / 100; lon < maxLon; lon += .02) {
    const x = xy({latitude:minLat, longitude:lon})[0];
    element('line', {x1:x, x2:x, y1:30, y2:730, class:'grid'});
    element('text', {x:x + 3, y:745}, svg, `${lon.toFixed(2)}°E`);
  }
  const edgeEls = new Map(), stationEls = new Map();
  for (const edge of graph.edges) {
    const [x1,y1] = xy(nodes.get(edge.from_id)), [x2,y2] = xy(nodes.get(edge.to_id));
    edgeEls.set(edge.id, element('line', {x1,y1,x2,y2,class:'edge'}));
  }
  for (const node of nodes.values()) {
    const [x,y] = xy(node);
    const group = element('g', {});
    element('title', {}, group, `${node.id} ${node.name}`);
    const circle = element('circle', {cx:x, cy:y, r:node.kind === 'station' ? 5 : 3,
      class:node.kind === 'station' ? 'station' : 'junction'}, group);
    if (node.kind === 'station') {
      stationEls.set(node.id, circle);
      element('text', {x:x + 8, y:y - 7}, group, node.id);
    }
  }
  for (const station of stations) {
    for (const id of ['start','end']) {
      const option = document.createElement('option');
      option.value = station.station_no; option.textContent = `${station.station_no} ${station.station_name}`;
      $(id).append(option);
    }
  }
  $('start').value = '211'; $('end').value = '218';
  function renderRoute() {
    const route = shortestRoute(graph, $('start').value, $('end').value);
    const selectedEdges = new Set(route?.edgeIds), selectedStations = new Set(route?.stationIds);
    for (const [id, line] of edgeEls) {
      line.setAttribute('class', selectedEdges.has(id) ? 'edge selected' : 'edge');
      if (selectedEdges.has(id)) svg.append(line);
    }
    // Keep station markers above highlighted lines.
    for (const circle of stationEls.values()) svg.append(circle.parentElement);
    for (const [id,circle] of stationEls) circle.setAttribute('class',
      `station${selectedStations.has(id) ? ' selected' : ''}${id === $('start').value || id === $('end').value ? ' endpoint' : ''}`);
    $('station-list').replaceChildren();
    if (!route) { $('summary').textContent = '연결된 경로가 없습니다.'; $('detail').textContent = ''; return; }
    $('summary').textContent = route.stops === 0 ? '출발역과 도착역이 같습니다.' : `${route.stops}정거장 이동`;
    $('detail').textContent = route.stops === 0 ? '이동 없이 선택한 정거장에 도착합니다.' :
      `출발·도착 포함 ${route.stationIds.length}개 정거장 · 중간 경유 ${Math.max(0,route.stationIds.length - 2)}개. 같은 정거장 수의 경로가 있으면 하나를 표시합니다.`;
    for (const id of route.stationIds) {
      const li = document.createElement('li'); li.textContent = `${id} ${stationById.get(id).station_name}`;
      $('station-list').append(li);
    }
  }
  $('route-form').addEventListener('submit', event => { event.preventDefault(); renderRoute(); });
  $('swap').addEventListener('click', () => {
    const start = $('start').value; $('start').value = $('end').value; $('end').value = start; renderRoute();
  });
  for (const id of ['start','end','swap','search']) $(id).disabled = false;
  renderRoute();
} catch (error) {
  $('summary').textContent = '데이터를 불러오지 못했습니다.';
  $('detail').textContent = `${error.message} 저장소 루트에서 HTTP 서버를 실행하고 /web/tram/에 접속해 주세요.`;
}
