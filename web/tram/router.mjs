export function parseCSV(text) {
  const rows = []; let row = [], field = '', quoted = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && (c === ',' || c === '\n' || c === '\r')) {
      row.push(field); field = '';
      if (c !== ',') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        if (row.some(Boolean)) rows.push(row);
        row = [];
      }
    } else field += c;
  }
  if (quoted) throw new Error('CSV 따옴표 형식 오류');
  if (field || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift();
  return rows.map(values => Object.fromEntries(header.map((key, i) => [key, values[i] ?? ''])));
}

export function shortestRoute(graph, start, end) {
  const nodes = new Map(graph.nodes.map(n => [n.id, n]));
  if (!nodes.has(start) || !nodes.has(end)) throw new Error('정거장을 찾을 수 없습니다.');
  const adjacent = new Map([...nodes.keys()].map(id => [id, []]));
  for (const edge of graph.edges) {
    if (edge.forward_allowed) adjacent.get(edge.from_id).push({to: edge.to_id, edge: edge.id});
    if (edge.reverse_allowed) adjacent.get(edge.to_id).push({to: edge.from_id, edge: edge.id});
  }
  // Dijkstra: entering a station costs one; entering a junction costs zero.
  const distance = new Map([[start, 0]]), previous = new Map(), pending = new Set(nodes.keys());
  while (pending.size) {
    const current = [...pending].sort((a, b) => (distance.get(a) ?? Infinity) - (distance.get(b) ?? Infinity))[0];
    if (!Number.isFinite(distance.get(current))) break;
    pending.delete(current);
    if (current === end) break;
    for (const next of adjacent.get(current)) {
      const cost = distance.get(current) + (nodes.get(next.to).kind === 'station' ? 1 : 0);
      if (cost < (distance.get(next.to) ?? Infinity)) {
        distance.set(next.to, cost); previous.set(next.to, {id: current, edge: next.edge});
      }
    }
  }
  if (!distance.has(end)) return null;
  const nodeIds = [end], edgeIds = [];
  while (nodeIds[0] !== start) {
    const prev = previous.get(nodeIds[0]); nodeIds.unshift(prev.id); edgeIds.unshift(prev.edge);
  }
  return {nodeIds, edgeIds, stationIds: nodeIds.filter(id => nodes.get(id).kind === 'station'), stops: distance.get(end)};
}
