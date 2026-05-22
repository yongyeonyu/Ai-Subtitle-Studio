import Testing
@testable import AIStudioCore

struct RoughcutChunkPlannerTests {
    @Test func boundaryCandidatesPickNearestMidpoints() throws {
        let response = RoughcutChunkPlanner.boundaryCandidates(payload: [
            "source": "confirmed",
            "rows": [
                ["start": 0.0, "end": 1.0],
                ["start": 1.5, "end": 2.0],
                ["start": 2.4, "end": 3.0],
                ["start": 3.4, "end": 4.0],
            ],
            "boundary_rows": [
                ["time": 1.2],
                ["timeline_sec": 2.3],
                3.2,
            ],
        ])

        let candidates = try #require(response["candidates"] as? [[String: Any]])
        #expect(candidates.count == 3)
        #expect(candidates.compactMap { $0["end_index"] as? Int } == [0, 1, 2])
        #expect(candidates.compactMap { $0["source"] as? String } == ["confirmed", "confirmed", "confirmed"])
    }

    @Test func duplicateMidpointTieKeepsEarlierIndex() throws {
        let response = RoughcutChunkPlanner.boundaryCandidates(payload: [
            "rows": [
                ["start": 0.0, "end": 1.0],
                ["start": 1.0, "end": 1.0],
                ["start": 1.0, "end": 1.0],
                ["start": 1.0, "end": 2.0],
            ],
            "boundary_rows": [2.0],
        ])

        let candidates = try #require(response["candidates"] as? [[String: Any]])
        #expect(candidates.count == 1)
        #expect(candidates[0]["end_index"] as? Int == 0)
    }
}
