import Foundation

public enum RoughcutChunkPlanner {
    public static func boundaryCandidates(payload: [String: Any]) -> [String: Any] {
        let rows = payload["rows"] as? [[String: Any]] ?? []
        let boundaryRows = payload["boundary_rows"] as? [Any] ?? []
        let source = stringValue(payload["source"], defaultValue: "boundary")
        guard rows.count >= 2, !boundaryRows.isEmpty else {
            return ["candidates": [], "backend": "swift"]
        }

        var midpoints: [(index: Int, value: Double)] = []
        midpoints.reserveCapacity(max(0, rows.count - 1))
        var lastValue: Double?
        for index in 0..<(rows.count - 1) {
            let end = doubleValue(rows[index]["end"], defaultValue: 0)
            let nextStart = doubleValue(rows[index + 1]["start"], defaultValue: end)
            let midpoint = (end + nextStart) / 2.0
            if let lastValue, midpoint < lastValue {
                return ["error": "rows must be sorted by midpoint for native roughcut planning"]
            }
            lastValue = midpoint
            midpoints.append((index: index, value: midpoint))
        }

        let midpointValues = midpoints.map(\.value)
        var bestByIndex: [Int: [String: Any]] = [:]
        for item in boundaryRows {
            guard let boundaryTime = boundaryTime(item) else { continue }
            guard let nearest = nearestMidpoint(midpoints: midpoints, values: midpointValues, time: boundaryTime) else {
                continue
            }
            let current = bestByIndex[nearest.index]
            if current == nil || nearest.distance < doubleValue(current?["distance"], defaultValue: Double.greatestFiniteMagnitude) {
                bestByIndex[nearest.index] = [
                    "end_index": nearest.index,
                    "source": source,
                    "distance": nearest.distance,
                    "time": boundaryTime,
                ]
            }
        }

        let candidates = bestByIndex.keys.sorted().compactMap { bestByIndex[$0] }
        return ["candidates": candidates, "backend": "swift"]
    }

    private static func nearestMidpoint(
        midpoints: [(index: Int, value: Double)],
        values: [Double],
        time: Double
    ) -> (index: Int, distance: Double)? {
        guard !midpoints.isEmpty else { return nil }
        let position = lowerBound(values, time)
        var candidatePositions: [Int] = []
        if position < values.count {
            candidatePositions.append(position)
        }
        if position > 0 {
            let leftValue = values[position - 1]
            candidatePositions.append(lowerBound(values, leftValue))
        }
        let bestPosition = candidatePositions.min { left, right in
            let leftDistance = abs(values[left] - time)
            let rightDistance = abs(values[right] - time)
            if leftDistance == rightDistance {
                return left < right
            }
            return leftDistance < rightDistance
        }
        guard let bestPosition else { return nil }
        return (index: midpoints[bestPosition].index, distance: abs(values[bestPosition] - time))
    }

    private static func lowerBound(_ values: [Double], _ target: Double) -> Int {
        var low = 0
        var high = values.count
        while low < high {
            let mid = (low + high) / 2
            if values[mid] < target {
                low = mid + 1
            } else {
                high = mid
            }
        }
        return low
    }

    private static func boundaryTime(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String { return Double(value) }
        guard let row = value as? [String: Any] else { return nil }
        for key in ["timeline_sec", "time", "sec", "timestamp", "start", "at"] {
            if let parsed = optionalDouble(row[key]) {
                return parsed
            }
        }
        return nil
    }

    private static func optionalDouble(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String { return Double(value) }
        return nil
    }

    private static func doubleValue(_ value: Any?, defaultValue: Double) -> Double {
        optionalDouble(value) ?? defaultValue
    }

    private static func stringValue(_ value: Any?, defaultValue: String = "") -> String {
        guard let value else { return defaultValue }
        let text = String(describing: value)
        return text.isEmpty ? defaultValue : text
    }
}
