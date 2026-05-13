import XCTest
@testable import AIStudioCore

final class CutBoundaryCachePlannerTests: XCTestCase {
    func testSettingsPayloadUsesDurationBucketAndResolution() throws {
        let response = CutBoundaryCachePlanner.settingsPayload(
            payload: [
                "settings": [
                    "cut_boundary_media_duration_sec": 1_800.0,
                    "scan_cut_compare_max_width": 1280,
                    "scan_cut_compare_max_height": 720,
                    "scan_cut_boundary_level": "auto",
                    "scan_cut_boundary_resolved_level": "low",
                ]
            ]
        )
        let settings = try XCTUnwrap(response["settings_payload"] as? [String: Any])
        XCTAssertEqual(settings["cut_boundary_media_duration_bucket_sec"] as? Int, 1800)
        XCTAssertEqual(settings["scan_cut_compare_max_width"] as? Int, 1280)
        XCTAssertEqual(settings["scan_cut_compare_max_height"] as? Int, 720)
        XCTAssertEqual(settings["scan_cut_boundary_resolved_level"] as? String, "low")
    }

    func testPlanChangesCachePathWhenResolutionChanges() throws {
        let files: [[String: Any]] = [
            [
                "path": "/tmp/demo.mp4",
                "size": 123,
                "mtime_ns": 456,
                "fingerprint_digest": "abc",
            ]
        ]
        let first = CutBoundaryCachePlanner.plan(
            payload: [
                "files": files,
                "settings": [:],
                "cache_root": "/tmp/cache",
                "version": 7,
                "cut_boundary_api_version": "v1",
                "cut_boundary_algorithm_version": "v2",
                "cut_boundary_algorithm_id": "algo",
            ]
        )
        let second = CutBoundaryCachePlanner.plan(
            payload: [
                "files": files,
                "settings": [
                    "scan_cut_compare_max_width": 1280,
                    "scan_cut_compare_max_height": 720,
                ],
                "cache_root": "/tmp/cache",
                "version": 7,
                "cut_boundary_api_version": "v1",
                "cut_boundary_algorithm_version": "v2",
                "cut_boundary_algorithm_id": "algo",
            ]
        )
        XCTAssertNotEqual(first["cache_path"] as? String, second["cache_path"] as? String)
    }
}
