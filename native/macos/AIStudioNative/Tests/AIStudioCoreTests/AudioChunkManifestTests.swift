import XCTest
@testable import AIStudioCore

final class AudioChunkManifestTests: XCTestCase {
    func testAudioChunkManifestParsesStartsAndDurations() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("audio-chunk-manifest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        try writeSilentWav(dir.appendingPathComponent("vad_002_3.500.wav"), sampleRate: 16_000, frames: 8_000)
        try writeSilentWav(dir.appendingPathComponent("vad_001_0.000.wav"), sampleRate: 16_000, frames: 16_000)

        let response = AudioChunkManifest.manifest(payload: ["chunk_dir": dir.path])
        XCTAssertNil(response["error"])
        let chunks = try XCTUnwrap(response["chunks"] as? [[String: Any]])
        XCTAssertEqual(chunks.count, 2)
        XCTAssertEqual(chunks[0]["name"] as? String, "vad_001_0.000.wav")
        XCTAssertEqual(chunks[0]["start"] as? Double ?? -1, 0.0, accuracy: 0.001)
        XCTAssertEqual(chunks[0]["duration"] as? Double ?? -1, 1.0, accuracy: 0.001)
        XCTAssertEqual(chunks[1]["start"] as? Double ?? -1, 3.5, accuracy: 0.001)
        XCTAssertEqual(chunks[1]["duration"] as? Double ?? -1, 0.5, accuracy: 0.001)
    }

    func testAudioChunkManifestCanRequireVADStart() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("audio-chunk-manifest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        try writeSilentWav(dir.appendingPathComponent("plain.wav"), sampleRate: 16_000, frames: 1_600)
        try writeSilentWav(dir.appendingPathComponent("vad_000_2.000.wav"), sampleRate: 16_000, frames: 1_600)

        let response = AudioChunkManifest.manifest(payload: [
            "chunk_dir": dir.path,
            "require_vad_start": true,
        ])
        let chunks = try XCTUnwrap(response["chunks"] as? [[String: Any]])
        XCTAssertEqual(chunks.map { $0["name"] as? String }, ["vad_000_2.000.wav"])
    }

    func testAudioChunkManifestMatchesPythonVADNameSuffixParsing() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("audio-chunk-manifest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        try writeSilentWav(dir.appendingPathComponent("clip_vad_003_.500.wav"), sampleRate: 16_000, frames: 1_600)

        let response = AudioChunkManifest.manifest(payload: ["chunk_dir": dir.path])
        let chunks = try XCTUnwrap(response["chunks"] as? [[String: Any]])
        XCTAssertEqual(chunks.count, 1)
        XCTAssertEqual(chunks[0]["name"] as? String, "clip_vad_003_.500.wav")
        XCTAssertEqual(chunks[0]["start"] as? Double ?? -1, 0.5, accuracy: 0.001)
        XCTAssertEqual(chunks[0]["duration"] as? Double ?? -1, 0.1, accuracy: 0.001)
    }

    private func writeSilentWav(_ url: URL, sampleRate: UInt32, frames: UInt32) throws {
        var data = Data()
        let channels: UInt16 = 1
        let bitsPerSample: UInt16 = 16
        let bytesPerFrame = UInt32(channels) * UInt32(bitsPerSample / 8)
        let byteRate = sampleRate * bytesPerFrame
        let dataSize = frames * bytesPerFrame

        data.appendASCII("RIFF")
        data.appendUInt32LE(36 + dataSize)
        data.appendASCII("WAVE")
        data.appendASCII("fmt ")
        data.appendUInt32LE(16)
        data.appendUInt16LE(1)
        data.appendUInt16LE(channels)
        data.appendUInt32LE(sampleRate)
        data.appendUInt32LE(byteRate)
        data.appendUInt16LE(UInt16(bytesPerFrame))
        data.appendUInt16LE(bitsPerSample)
        data.appendASCII("data")
        data.appendUInt32LE(dataSize)
        data.append(Data(repeating: 0, count: Int(dataSize)))
        try data.write(to: url)
    }
}

private extension Data {
    mutating func appendASCII(_ value: String) {
        append(Data(value.utf8))
    }

    mutating func appendUInt16LE(_ value: UInt16) {
        append(UInt8(value & 0xff))
        append(UInt8((value >> 8) & 0xff))
    }

    mutating func appendUInt32LE(_ value: UInt32) {
        append(UInt8(value & 0xff))
        append(UInt8((value >> 8) & 0xff))
        append(UInt8((value >> 16) & 0xff))
        append(UInt8((value >> 24) & 0xff))
    }
}
