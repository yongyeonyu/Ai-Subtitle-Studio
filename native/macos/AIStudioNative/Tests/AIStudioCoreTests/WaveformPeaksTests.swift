import XCTest
@testable import AIStudioCore

final class WaveformPeaksTests: XCTestCase {
    func testDownsampleF32LENormalizesPeaks() {
        var samples = Array(repeating: Float(0), count: 2_000)
        for index in 100..<110 {
            samples[index] = 0.5
        }
        for index in 1_000..<1_010 {
            samples[index] = -1.0
        }
        let data = samples.withUnsafeBufferPointer { buffer in
            Data(buffer: buffer)
        }

        let result = WaveformPeaks.downsampleF32LE(data)

        XCTAssertEqual(result.waveform.count, 100)
        XCTAssertEqual(result.duration, 1.0, accuracy: 0.001)
        XCTAssertEqual(result.waveform.max() ?? 0, 1.0, accuracy: 0.0001)
    }

    func testDecodeF32LEIgnoresTrailingBytes() {
        var one = Float(1.0).bitPattern.littleEndian
        var minusHalf = Float(-0.5).bitPattern.littleEndian
        var data = Data(bytes: &one, count: 4)
        data.append(Data(bytes: &minusHalf, count: 4))
        data.append(0xff)

        let decoded = WaveformPeaks.decodeF32LE(data)

        XCTAssertEqual(decoded.count, 2)
        XCTAssertEqual(decoded[0], 1.0, accuracy: 0.0001)
        XCTAssertEqual(decoded[1], -0.5, accuracy: 0.0001)
    }
}
