import XCTest
@testable import AIStudioCore

final class StartupDiagnosticsNativeTests: XCTestCase {
    func testBuildProducesPreciseProfile() throws {
        let response = StartupDiagnosticsNative.build(
            payload: [
                "media_path": "/tmp/source/틴니핑.MP4",
                "media_name": "틴니핑.MP4",
                "media": [
                    "duration_sec": 1450.249,
                    "fps": 59.94,
                    "width": 3840,
                    "height": 2160,
                    "info_txt": "3840x2160 (59.94fps)",
                ],
                "audio": [
                    "has_audio": true,
                    "codec": "aac",
                    "sample_rate": 48_000,
                    "channels": 2,
                    "bit_rate": 160_000,
                    "duration_sec": 1450.249,
                ],
                "settings": ["max_speakers": 2],
                "cut_boundaries": [["timeline_sec": 120.0], ["timeline_sec": 300.0]],
                "provisional_cut_boundaries": [["timeline_sec": 180.0]],
                "expected_time_sec": 321.0,
            ]
        )

        let media = try XCTUnwrap(response["media"] as? [String: Any])
        let audio = try XCTUnwrap(response["audio"] as? [String: Any])
        let quality = try XCTUnwrap(audio["quality"] as? [String: Any])
        let cutDensity = try XCTUnwrap(response["cut_density"] as? [String: Any])
        let recommendation = try XCTUnwrap(response["recommended_pipeline"] as? [String: Any])

        XCTAssertEqual(response["schema"] as? String, "ai_subtitle_studio.startup_diagnostic.v1")
        XCTAssertEqual(media["duration_label"] as? String, "24:10")
        XCTAssertEqual(quality["label"] as? String, "green")
        XCTAssertEqual(cutDensity["verified_count"] as? Int, 2)
        XCTAssertEqual(recommendation["mode"] as? String, "precise")
        XCTAssertEqual(response["estimated_processing_label"] as? String, "5분 21초")
    }

    func testFormatLogContainsModeAndDuration() throws {
        let response = StartupDiagnosticsNative.formatLog(
            payload: [
                "diagnostic": [
                    "media_name": "clip.mp4",
                    "media": [
                        "duration_label": "24:10",
                        "fps": 59.94,
                        "width": 3840,
                        "height": 2160,
                    ],
                    "audio": [
                        "sample_rate": 48_000,
                        "channels": 2,
                        "quality": [
                            "summary": "양호",
                            "noise_label": "낮음",
                        ],
                    ],
                    "cut_density": [
                        "label": "중간",
                        "verified_count": 2,
                        "provisional_count": 1,
                        "per_minute": 1.23,
                    ],
                    "recommended_pipeline": [
                        "label": "정밀 모드",
                        "reasons": ["long_video", "high_fps"],
                    ],
                    "estimated_processing_label": "5분 21초",
                ]
            ]
        )
        let lines = try XCTUnwrap(response["lines"] as? [String])
        XCTAssertTrue(lines.contains(where: { $0.contains("정밀 모드") }))
        XCTAssertTrue(lines.contains(where: { $0.contains("24:10") }))
    }
}
