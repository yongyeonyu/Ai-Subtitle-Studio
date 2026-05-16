import XCTest
@testable import AIStudioCore

final class MediaProbeNativeTests: XCTestCase {
    func testNormalizeUsesVideoStreamMetadata() throws {
        let response = MediaProbeNative.normalize(
            payload: [
                "probe_json": """
                {
                  "format": {"duration": "8.4", "bit_rate": "42100000"},
                  "streams": [{
                    "duration": "8.4",
                    "width": 3840,
                    "height": 2160,
                    "r_frame_rate": "60000/1001",
                    "bit_rate": "42100000",
                    "pix_fmt": "yuv420p10le",
                    "color_space": "bt709",
                    "color_transfer": "bt709",
                    "color_primaries": "bt709",
                    "codec_name": "hevc",
                    "profile": "Main 10",
                    "bits_per_raw_sample": "10"
                  }]
                }
                """
            ]
        )
        let result = try XCTUnwrap(response["result"] as? [String: Any])

        XCTAssertEqual(result["bit_rate"] as? Int, 42_100_000)
        XCTAssertEqual(result["pix_fmt"] as? String, "yuv420p10le")
        XCTAssertEqual(result["color_space"] as? String, "bt709")
        XCTAssertEqual(result["codec_name"] as? String, "hevc")
        XCTAssertEqual(result["profile"] as? String, "Main 10")
        XCTAssertEqual(result["bits_per_raw_sample"] as? Int, 10)
        XCTAssertEqual(result["len_txt"] as? String, "00:08")
    }

    func testNormalizeKeepsAudioDefaultsForMissingVideoStream() throws {
        let response = MediaProbeNative.normalize(
            payload: [
                "probe_json": """
                {
                  "format": {"duration": "61.2"},
                  "streams": []
                }
                """
            ]
        )
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        let duration = try XCTUnwrap(result["duration"] as? Double)

        XCTAssertEqual(duration, 61.2, accuracy: 0.0001)
        XCTAssertEqual(result["info_txt"] as? String, "오디오 파일")
        XCTAssertEqual(result["len_txt"] as? String, "01:01")
    }
}
