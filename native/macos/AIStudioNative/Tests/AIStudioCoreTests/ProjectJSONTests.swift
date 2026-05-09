import XCTest
@testable import AIStudioCore

final class ProjectJSONTests: XCTestCase {
    func testNormalizedDataStripsRuntimeKeysAndPreservesUnicode() throws {
        let project: [String: Any] = [
            "app": "AI Subtitle Studio",
            "project_name": "테스트",
            "_project_file_path": "/tmp/private.json",
            "analysis": [
                "stt_candidate_tracks": [
                    "STT1": [["start": 0.0, "end": 1.0, "text": "안녕하세요"]]
                ]
            ],
        ]

        let data = try ProjectJSON.normalizedData(from: project)
        let text = String(data: data, encoding: .utf8) ?? ""

        XCTAssertTrue(text.contains("테스트"))
        XCTAssertFalse(text.contains("_project_file_path"))
        XCTAssertTrue(text.hasSuffix("\n"))
    }

    func testAtomicWriteAndReadProjectObject() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ai-studio-native-tests-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }

        let url = root.appendingPathComponent("nested/project.json")
        let project: [String: Any] = [
            "app": "AI Subtitle Studio",
            "version": "03.25.01",
            "media": [["path": "/tmp/clip.mp4"]],
            "subtitles": ["storage": "external_srt"],
            "asset_storage": ["tracks": ["stt_stt1": ["path": "Assets/stt1.srt"]]],
        ]

        let data = try ProjectJSON.normalizedData(from: project)
        try ProjectJSON.atomicWrite(data, to: url)
        let loaded = try ProjectJSON.readObject(from: url)
        let summary = ProjectJSON.summary(for: loaded)

        XCTAssertEqual(summary["media_count"] as? Int, 1)
        XCTAssertEqual(summary["subtitle_storage"] as? String, "external_srt")
        XCTAssertEqual(summary["external_track_count"] as? Int, 1)
    }
}
