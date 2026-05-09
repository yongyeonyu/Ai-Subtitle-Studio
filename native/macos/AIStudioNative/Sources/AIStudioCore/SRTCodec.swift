import Foundation

public enum SRTCodecError: Error, LocalizedError {
    case unreadableFile(URL)
    case unencodableJSON

    public var errorDescription: String? {
        switch self {
        case .unreadableFile(let url):
            return "Unable to read SRT file: \(url.path)"
        case .unencodableJSON:
            return "Unable to encode subtitle JSON"
        }
    }
}

public enum SRTCodec {
    private static let timestampPattern =
        #"(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})"#

    public static func parseFile(_ url: URL) throws -> [SubtitleSegment] {
        let data = try Data(contentsOf: url)
        guard let content = decodeSRTData(data) else {
            throw SRTCodecError.unreadableFile(url)
        }
        return parse(content)
    }

    public static func parse(_ content: String) -> [SubtitleSegment] {
        let normalized = content
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return [] }

        let regex = try? NSRegularExpression(pattern: timestampPattern)
        var segments: [SubtitleSegment] = []
        for block in splitBlocks(normalized) {
            let lines = block
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map(String.init)
            guard lines.count >= 2 else { continue }

            var timestampLineIndex: Int?
            var match: NSTextCheckingResult?
            for (idx, line) in lines.enumerated() {
                let range = NSRange(line.startIndex..<line.endIndex, in: line)
                if let found = regex?.firstMatch(in: line, range: range) {
                    timestampLineIndex = idx
                    match = found
                    break
                }
            }
            guard
                let timestampLineIndex,
                let match,
                match.numberOfRanges >= 3
            else { continue }

            let line = lines[timestampLineIndex]
            guard
                let startRange = Range(match.range(at: 1), in: line),
                let endRange = Range(match.range(at: 2), in: line),
                let start = parseTimestamp(String(line[startRange])),
                let end = parseTimestamp(String(line[endRange]))
            else { continue }

            let text = lines[(timestampLineIndex + 1)...]
                .joined(separator: "\n")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }

            segments.append(SubtitleSegment(start: start, end: end, text: text))
        }
        return segments
    }

    public static func format(_ segments: [SubtitleSegment]) -> String {
        var out: [String] = []
        var index = 1
        for segment in segments {
            let text = segment.text
                .replacingOccurrences(of: "\u{2028}", with: "\n")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty, text != "\u{200B}" else { continue }

            let start = max(0, segment.start)
            let end = max(start + 0.1, segment.end)
            out.append(String(index))
            out.append("\(formatTimestamp(start)) --> \(formatTimestamp(end))")
            out.append(text)
            out.append("")
            index += 1
        }
        return out.joined(separator: "\n")
    }

    public static func parseTimestamp(_ raw: String) -> Double? {
        let parts = raw.replacingOccurrences(of: ",", with: ".").split(separator: ":")
        guard parts.count == 3,
              let hours = Double(parts[0]),
              let minutes = Double(parts[1]),
              let seconds = Double(parts[2]) else {
            return nil
        }
        return hours * 3600 + minutes * 60 + seconds
    }

    public static func formatTimestamp(_ seconds: Double) -> String {
        let totalMilliseconds = max(0, Int((seconds * 1000).rounded()))
        let hours = totalMilliseconds / 3_600_000
        let minutes = (totalMilliseconds % 3_600_000) / 60_000
        let secs = (totalMilliseconds % 60_000) / 1000
        let millis = totalMilliseconds % 1000
        return String(format: "%02d:%02d:%02d,%03d", hours, minutes, secs, millis)
    }

    private static func splitBlocks(_ content: String) -> [String] {
        var blocks: [String] = []
        var current: [String] = []
        for line in content.split(separator: "\n", omittingEmptySubsequences: false).map(String.init) {
            if line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                if !current.isEmpty {
                    blocks.append(current.joined(separator: "\n"))
                    current.removeAll(keepingCapacity: true)
                }
            } else {
                current.append(line)
            }
        }
        if !current.isEmpty {
            blocks.append(current.joined(separator: "\n"))
        }
        return blocks
    }

    private static func decodeSRTData(_ data: Data) -> String? {
        if let text = String(data: data, encoding: .utf8) {
            return text
        }
        if let text = String(data: data, encoding: .utf16) {
            return text
        }
        if let text = String(data: data, encoding: .utf16LittleEndian) {
            return text
        }
        if let text = String(data: data, encoding: .utf16BigEndian) {
            return text
        }
        return nil
    }
}
