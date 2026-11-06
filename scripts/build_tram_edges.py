"""Build schematic routing connections from existing tram station coordinates.

Run: python scripts/build_tram_edges.py
Only data/tram_edges.json is written. No network or third-party packages needed.
"""

import csv
import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def main():
    source = DATA / "tram_stations_estimated.csv"
    original = source.read_bytes()
    rows = list(csv.DictReader(original.decode("utf-8-sig").splitlines()))
    counts = Counter(r["station_no"] for r in rows)
    expected = {str(n) for n in range(201, 246)}
    assert set(counts) == expected and all(n == 1 for n in counts.values())
    nodes = {}
    for r in rows:
        lat, lon = float(r["latitude"]), float(r["longitude"])
        assert 36.2 <= lat <= 36.5 and 127.2 <= lon <= 127.6
        nodes[r["station_no"]] = dict(
            id=r["station_no"], kind="station", name=r["station_name"],
            latitude=lat, longitude=lon, position_type=r["position_type"],
            confidence=r["confidence"], source_page=r["source_page"],
        )

    # Reuse the previously saved junction point; never recalculate station coordinates.
    previous = json.loads((DATA / "tram_route_graph.json").read_text(encoding="utf-8"))
    junction = next(n for n in previous["nodes"] if n["id"] == "J_중리")
    nodes["J_중리"] = {**junction, "position_type": "existing_schematic_junction",
                          "coordinate_source": "tram_route_graph.json"}
    loop = [str(n) for n in range(201, 241)]
    loop.insert(loop.index("213"), "J_중리")
    loop.append("201")
    sections = [
        dict(id="main_loop", closed=True, node_sequence=loop),
        dict(id="yeonchuk_branch", closed=False,
             node_sequence=["J_중리", "241", "242", "243", "244"]),
        dict(id="jinjam_branch", closed=False, node_sequence=["233", "245"]),
    ]
    edges, arcs = [], []
    adjacency = defaultdict(set)
    for section in sections:
        for a, b in zip(section["node_sequence"], section["node_sequence"][1:]):
            edge_id = f"e{len(edges) + 1:03d}"
            edges.append(dict(
                id=edge_id, from_id=a, to_id=b, section=section["id"],
                forward_allowed=True, reverse_allowed=True,
                direction_basis="virtual_navigation_assumption", source_page=2,
                geometry_type="schematic_straight_connection",
                geometry=dict(type="LineString", coordinates=[
                    [nodes[n]["longitude"], nodes[n]["latitude"]] for n in (a, b)]),
            ))
            for start, end in ((a, b), (b, a)):
                arcs.append(dict(edge_id=edge_id, from_id=start, to_id=end))
                adjacency[start].add(end)

    reachable_pairs = 0
    unreachable = []
    for start in sorted(expected):
        seen, queue = {start}, deque([start])
        while queue:
            for end in adjacency[queue.popleft()] - seen:
                seen.add(end)
                queue.append(end)
        for end in sorted(expected - {start}):
            if end in seen:
                reachable_pairs += 1
            else:
                unreachable.append([start, end])
    assert not unreachable
    assert len(edges) == len({tuple(sorted((e["from_id"], e["to_id"]))) for e in edges})
    assert all(a in nodes and b in nodes for a, ends in adjacency.items() for b in ends)
    assert adjacency["J_중리"] == {"212", "213", "241"}
    assert adjacency["233"] == {"232", "234", "245"}
    assert adjacency["244"] == {"243"} and adjacency["245"] == {"233"}
    assert len(edges) - len(nodes) + 1 == 1
    assert source.read_bytes() == original

    result = dict(
        schema_version=1, coordinate_reference_system="EPSG:4326",
        description="대전 2호선 가상 내비게이션용 정거장 연결 그래프. 선은 실제 선로가 아닌 직선 개략 연결이다.",
        sources=dict(
            station_coordinates="tram_stations_estimated.csv",
            station_csv_sha256=hashlib.sha256(original).hexdigest(),
            official_route="../../tram-investigation/sources/station_locations.pdf#page=2",
            official_route_url="https://www.daejeon.go.kr/djTram/notify/normalBoardDetail.do?boardId=djTram_0001&menuSeq=6724&ntatcSeq=1464065145",
        ),
        routing_policy=dict(
            bidirectional=True,
            basis="가상 경로 탐색을 위해 모든 연결을 양방향으로 가정한다. 공식 위치도는 연결 관계의 근거이며 실제 운행 방향·운행계통의 근거가 아니다.",
            junction_transitions="연결된 모든 간선 간 이동을 허용하는 논리 모델. 실제 분기기 전환·직결 운행·환승 가능 여부는 미검증.",
            weights="없음. 이동시간·도보거리·실제 선로 거리를 제공하지 않는다.",
        ),
        junctions=[
            dict(node_id="J_중리", can_branch=True, can_merge=True,
                 main_neighbors=["212", "213"], branch_neighbor="241",
                 location_basis="공식 전체 노선도에서 212·213 사이 분기. 기존 분석의 분기점 좌표 재사용."),
            dict(node_id="233", can_branch=True, can_merge=True,
                 main_neighbors=["232", "234"], branch_neighbor="245",
                 location_basis="233 인근 진잠 지선을 233 정거장에 논리적으로 접속. 실제 분기기와 승강장이 같은 위치라는 의미가 아니다."),
        ],
        sections=sections, nodes=list(nodes.values()), edges=edges, routing_arcs=arcs,
        validation=dict(
            station_count=len(rows), missing_station_numbers=[], duplicate_station_numbers=[],
            out_of_range_coordinates=[], node_count=len(nodes),
            physical_connection_count=len(edges), directed_arc_count=len(arcs),
            independent_cycle_count=1, branch_terminal_ids=["244", "245"],
            reachable_ordered_station_pairs=reachable_pairs,
            expected_ordered_station_pairs=45 * 44, unreachable_station_pairs=unreachable,
            original_station_csv_unchanged=True,
            scope="번호·좌표 범위·노선 순서·양방향 그래프 도달성. 좌표 정밀도와 실제 운행은 검증 범위 밖이다.",
        ),
    )
    output = DATA / "tram_edges.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["validation"], ensure_ascii=False))


if __name__ == "__main__":
    main()
