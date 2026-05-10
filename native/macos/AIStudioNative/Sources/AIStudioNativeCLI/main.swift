import AIStudioCore
import Foundation

enum CLIError: Error, LocalizedError {
    case usage(String)
    case unsupportedCommand(String)

    var errorDescription: String? {
        switch self {
        case .usage(let message):
            return message
        case .unsupportedCommand(let command):
            return "Unsupported command: \(command)"
        }
    }
}

func printUsage() {
    FileHandle.standardError.write(Data("""
    AIStudioNativeCLI

    Commands:
      version
      srt-to-json <input.srt>
      json-to-srt <input.json> [output.srt]
      validate-srt <input.srt>
      core-jsonl-worker
      read-project-json <project.json>
      write-project-json <project.json>
      project-summary <project.json>
      waveform-peaks-f32le [--sample-rate 2000] [--points-per-second 100] [--duration sec]
      timeline-waveform-columns-f32le --width px --total sec [--vad-json json]
      timeline-segment-layout-json
      timeline-playhead-dirty-json
      timeline-timing-drag-json
      timeline-subtitle-merge-preview-json
      timeline-subtitle-magnet-json
      timeline-undo-snapshot-json
      timeline-live-subtitle-preview-json
      timeline-stt-candidate-selection-json
      timeline-srt-metadata-match-json
      timeline-editor-load-prep-json
      timeline-drag-snap-base-json
      timeline-segment-timing-edit-plan-json
      timeline-layout-jsonl-worker
      quality-score-json
      quality-score-jsonl-worker
      common-split-plan-json
      common-split-plan-jsonl-worker
      native-policy-llm-candidates-json
      native-policy-llm-candidates-batch-json
      native-policy-deep-rerank-json
      native-policy-deep-rerank-batch-json
      native-policy-lora-score-json
      native-policy-jsonl-worker
      native-memory-snapshot-json

    """.utf8))
}

func run() throws {
    var args = CommandLine.arguments.dropFirst()
    guard let command = args.first else {
        printUsage()
        throw CLIError.usage("Missing command")
    }
    args = args.dropFirst()

    switch command {
    case "version":
        print("AIStudioNativeCLI 0.1")

    case "srt-to-json":
        guard let path = args.first else {
            throw CLIError.usage("srt-to-json requires an input path")
        }
        let segments = try SRTCodec.parseFile(URL(fileURLWithPath: path))
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(segments)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "json-to-srt":
        guard let input = args.first else {
            throw CLIError.usage("json-to-srt requires an input JSON path")
        }
        let data = try Data(contentsOf: URL(fileURLWithPath: input))
        let segments = try JSONDecoder().decode([SubtitleSegment].self, from: data)
        let srt = SRTCodec.format(segments)
        if args.count >= 2 {
            let output = Array(args)[1]
            try srt.write(to: URL(fileURLWithPath: output), atomically: true, encoding: .utf8)
        } else {
            print(srt)
        }

    case "validate-srt":
        guard let path = args.first else {
            throw CLIError.usage("validate-srt requires an input path")
        }
        let segments = try SRTCodec.parseFile(URL(fileURLWithPath: path))
        print("segments=\(segments.count)")

    case "core-jsonl-worker":
        while let line = readLine(strippingNewline: true) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            do {
                let data = Data(trimmed.utf8)
                let payload = (try JSONSerialization.jsonObject(with: data, options: [])) as? [String: Any] ?? [:]
                let task = String(describing: payload["task"] ?? "")
                let response: [String: Any]
                switch task {
                case "srt_to_json":
                    let path = String(describing: payload["path"] ?? "")
                    if path.isEmpty {
                        response = ["error": "Missing SRT path"]
                    } else {
                        let segments = try SRTCodec.parseFile(URL(fileURLWithPath: path))
                        response = ["segments": try jsonValue(from: segments)]
                    }
                case "read_project_json":
                    let path = String(describing: payload["path"] ?? "")
                    if path.isEmpty {
                        response = ["error": "Missing project path"]
                    } else {
                        let object = try ProjectJSON.readObject(from: URL(fileURLWithPath: path))
                        response = ["project": object]
                    }
                case "write_project_json":
                    let path = String(describing: payload["path"] ?? "")
                    guard !path.isEmpty else {
                        response = ["error": "Missing project path"]
                        try writeJSONObject(response)
                        continue
                    }
                    let project = payload["project"] as? [String: Any] ?? [:]
                    let normalized = try ProjectJSON.normalizedData(from: project)
                    try ProjectJSON.atomicWrite(normalized, to: URL(fileURLWithPath: path))
                    response = ["ok": true]
                case "project_summary":
                    let path = String(describing: payload["path"] ?? "")
                    if path.isEmpty {
                        response = ["error": "Missing project path"]
                    } else {
                        let object = try ProjectJSON.readObject(from: URL(fileURLWithPath: path))
                        response = ["summary": ProjectJSON.summary(for: object)]
                    }
                default:
                    response = ["error": "Unsupported core task: \(task)"]
                }
                try writeJSONObject(response)
            } catch {
                let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
                try writeJSONObject(["error": message])
            }
        }

    case "read-project-json":
        guard let path = args.first else {
            throw CLIError.usage("read-project-json requires an input path")
        }
        let object = try ProjectJSON.readObject(from: URL(fileURLWithPath: path))
        let data = try ProjectJSON.normalizedData(from: object)
        FileHandle.standardOutput.write(data)

    case "write-project-json":
        guard let path = args.first else {
            throw CLIError.usage("write-project-json requires an output path")
        }
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let data = try ProjectJSON.normalizedData(fromJSONData: input)
        try ProjectJSON.atomicWrite(data, to: URL(fileURLWithPath: path))

    case "project-summary":
        guard let path = args.first else {
            throw CLIError.usage("project-summary requires an input path")
        }
        let object = try ProjectJSON.readObject(from: URL(fileURLWithPath: path))
        let data = try ProjectJSON.normalizedData(from: ProjectJSON.summary(for: object))
        FileHandle.standardOutput.write(data)

    case "waveform-peaks-f32le":
        let options = parseWaveformOptions(Array(args))
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let result = WaveformPeaks.downsampleF32LE(
            input,
            sampleRate: options.sampleRate,
            pointsPerSecond: options.pointsPerSecond,
            duration: options.duration
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(result)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-waveform-columns-f32le":
        let options = parseTimelineColumnOptions(Array(args))
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let waveform = WaveformPeaks.decodeF32LE(input)
        let columns = TimelineColumns.buildWaveformColumns(
            waveform: waveform,
            width: options.width,
            totalDuration: options.totalDuration,
            vadSegments: options.vadSegments
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(columns)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-segment-layout-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSegmentLayoutRequest.self, from: input)
        let response = TimelineLayout.segmentLayouts(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-playhead-dirty-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelinePlayheadDirtyRequest.self, from: input)
        let response = TimelineLayout.playheadDirtyRect(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-timing-drag-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineTimingDragRequest.self, from: input)
        let response = TimelineEditing.apply(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-subtitle-merge-preview-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSubtitleMergePreviewRequest.self, from: input)
        let response = TimelineEditing.mergePreview(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-subtitle-magnet-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSubtitleMagnetRequest.self, from: input)
        let response = TimelineEditing.subtitleMagnet(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-undo-snapshot-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineUndoSnapshotRequest.self, from: input)
        let response = TimelineEditing.undoSnapshot(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-live-subtitle-preview-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineLiveSubtitlePreviewRequest.self, from: input)
        let response = TimelineEditing.liveSubtitlePreview(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-stt-candidate-selection-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSTTCandidateSelectionRequest.self, from: input)
        let response = TimelineEditing.sttCandidateSelection(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-srt-metadata-match-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSRTMetadataMatchRequest.self, from: input)
        let response = TimelineEditing.srtMetadataMatches(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-editor-load-prep-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineEditorLoadRequest.self, from: input)
        let response = TimelineEditing.prepareEditorSegmentsForLoad(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-drag-snap-base-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineDragSnapBaseRequest.self, from: input)
        let response = TimelineEditing.dragSnapBase(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-segment-timing-edit-plan-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(TimelineSegmentTimingEditPlanRequest.self, from: input)
        let response = TimelineEditing.segmentTimingEditPlan(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "timeline-layout-jsonl-worker":
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        while let line = readLine(strippingNewline: true) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            do {
                let data = Data(trimmed.utf8)
                let payload = (try JSONSerialization.jsonObject(with: data, options: [])) as? [String: Any] ?? [:]
                let task = String(describing: payload["task"] ?? "")
                switch task {
                case "segment_layout":
                    let request = try decoder.decode(TimelineSegmentLayoutRequest.self, from: data)
                    let response = TimelineLayout.segmentLayouts(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "playhead_dirty":
                    let request = try decoder.decode(TimelinePlayheadDirtyRequest.self, from: data)
                    let response = TimelineLayout.playheadDirtyRect(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "timing_drag":
                    let request = try decoder.decode(TimelineTimingDragRequest.self, from: data)
                    let response = TimelineEditing.apply(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "merge_preview":
                    let request = try decoder.decode(TimelineSubtitleMergePreviewRequest.self, from: data)
                    let response = TimelineEditing.mergePreview(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "subtitle_magnet":
                    let request = try decoder.decode(TimelineSubtitleMagnetRequest.self, from: data)
                    let response = TimelineEditing.subtitleMagnet(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "undo_snapshot":
                    let request = try decoder.decode(TimelineUndoSnapshotRequest.self, from: data)
                    let response = TimelineEditing.undoSnapshot(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "live_subtitle_preview":
                    let request = try decoder.decode(TimelineLiveSubtitlePreviewRequest.self, from: data)
                    let response = TimelineEditing.liveSubtitlePreview(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "stt_candidate_selection":
                    let request = try decoder.decode(TimelineSTTCandidateSelectionRequest.self, from: data)
                    let response = TimelineEditing.sttCandidateSelection(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "srt_metadata_match":
                    let request = try decoder.decode(TimelineSRTMetadataMatchRequest.self, from: data)
                    let response = TimelineEditing.srtMetadataMatches(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "editor_load_prep":
                    let request = try decoder.decode(TimelineEditorLoadRequest.self, from: data)
                    let response = TimelineEditing.prepareEditorSegmentsForLoad(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "drag_snap_base":
                    let request = try decoder.decode(TimelineDragSnapBaseRequest.self, from: data)
                    let response = TimelineEditing.dragSnapBase(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                case "segment_timing_edit_plan":
                    let request = try decoder.decode(TimelineSegmentTimingEditPlanRequest.self, from: data)
                    let response = TimelineEditing.segmentTimingEditPlan(request)
                    FileHandle.standardOutput.write(try encoder.encode(response))
                default:
                    let message = ["error": "Unsupported timeline layout task: \(task)"]
                    FileHandle.standardOutput.write(try encoder.encode(message))
                }
                FileHandle.standardOutput.write(Data("\n".utf8))
            } catch {
                let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
                let data = try encoder.encode(["error": message])
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data("\n".utf8))
            }
        }

    case "quality-score-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(QualityScoreRequest.self, from: input)
        let response = SubtitleQualityScorer.score(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "quality-score-jsonl-worker":
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        while let line = readLine(strippingNewline: true) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            do {
                let request = try decoder.decode(QualityScoreRequest.self, from: Data(trimmed.utf8))
                let response = SubtitleQualityScorer.score(request)
                let data = try encoder.encode(response)
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data("\n".utf8))
            } catch {
                let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
                let data = try encoder.encode(["error": message])
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data("\n".utf8))
            }
        }

    case "common-split-plan-json":
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = try JSONDecoder().decode(CommonSplitPlanRequest.self, from: input)
        let response = CommonSplitPlanner.plan(request)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))

    case "common-split-plan-jsonl-worker":
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        while let line = readLine(strippingNewline: true) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            do {
                let request = try decoder.decode(CommonSplitPlanRequest.self, from: Data(trimmed.utf8))
                let response = CommonSplitPlanner.plan(request)
                let data = try encoder.encode(response)
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data("\n".utf8))
            } catch {
                let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
                let data = try encoder.encode(["error": message])
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data("\n".utf8))
            }
        }

    case "native-policy-llm-candidates-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(NativePolicyEngine.llmCandidates(payload: payload))

    case "native-policy-llm-candidates-batch-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(NativePolicyEngine.llmCandidatesBatch(payload: payload))

    case "native-policy-deep-rerank-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(NativePolicyEngine.deepRerank(payload: payload))

    case "native-policy-deep-rerank-batch-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(NativePolicyEngine.deepRerankBatch(payload: payload))

    case "native-policy-lora-score-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(NativePolicyEngine.loraScore(payload: payload))

    case "native-memory-snapshot-json":
        let payload = try readJSONObjectFromStdin()
        try writeJSONObject(MemoryPressure.snapshot(payload: payload))

    case "native-policy-jsonl-worker":
        var cachedPolicyIndexes: [String: [String: Any]] = [:]
        while let line = readLine(strippingNewline: true) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                continue
            }
            do {
                let data = Data(trimmed.utf8)
                let payload = (try JSONSerialization.jsonObject(with: data, options: [])) as? [String: Any] ?? [:]
                let task = String(describing: payload["task"] ?? "")
                let response: [String: Any]
                switch task {
                case "llm_candidates":
                    response = NativePolicyEngine.llmCandidates(payload: payload)
                case "llm_candidates_batch":
                    response = NativePolicyEngine.llmCandidatesBatch(payload: payload)
                case "deep_rerank":
                    response = NativePolicyEngine.deepRerank(payload: payload)
                case "deep_rerank_batch":
                    response = NativePolicyEngine.deepRerankBatch(payload: payload)
                case "lora_index_put":
                    let indexID = String(describing: payload["index_id"] ?? "")
                    if indexID.isEmpty {
                        response = ["error": "Missing lora index_id"]
                    } else {
                        cachedPolicyIndexes[indexID] = payload["index"] as? [String: Any] ?? [:]
                        let docs = cachedPolicyIndexes[indexID]?["docs"] as? [[String: Any]] ?? []
                        response = ["ok": true, "index_id": indexID, "doc_count": docs.count]
                    }
                case "lora_index_clear":
                    cachedPolicyIndexes.removeAll()
                    response = ["ok": true]
                case "lora_score_cached":
                    let indexID = String(describing: payload["index_id"] ?? "")
                    if let index = cachedPolicyIndexes[indexID] {
                        var request = payload
                        request["index"] = index
                        response = NativePolicyEngine.loraScore(payload: request)
                    } else {
                        response = ["error": "Missing cached lora index: \(indexID)"]
                    }
                case "lora_score":
                    response = NativePolicyEngine.loraScore(payload: payload)
                default:
                    response = ["error": "Unsupported native policy task: \(task)"]
                }
                try writeJSONObject(response)
            } catch {
                let message = String(describing: error).replacingOccurrences(of: "\n", with: " ")
                try writeJSONObject(["error": message])
            }
        }

    default:
        printUsage()
        throw CLIError.unsupportedCommand(command)
    }
}

func readJSONObjectFromStdin() throws -> [String: Any] {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    guard !input.isEmpty else {
        return [:]
    }
    let decoded = try JSONSerialization.jsonObject(with: input, options: [])
    return decoded as? [String: Any] ?? [:]
}

func writeJSONObject(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

func jsonValue<T: Encodable>(from value: T) throws -> Any {
    let encoder = JSONEncoder()
    let data = try encoder.encode(value)
    return try JSONSerialization.jsonObject(with: data, options: [])
}

func parseWaveformOptions(_ args: [String]) -> (sampleRate: Int, pointsPerSecond: Int, duration: Double?) {
    var sampleRate = 2_000
    var pointsPerSecond = 100
    var duration: Double?
    var index = 0
    while index < args.count {
        let key = args[index]
        let value = index + 1 < args.count ? args[index + 1] : ""
        switch key {
        case "--sample-rate":
            sampleRate = Int(value) ?? sampleRate
            index += 2
        case "--points-per-second":
            pointsPerSecond = Int(value) ?? pointsPerSecond
            index += 2
        case "--duration":
            duration = Double(value)
            index += 2
        default:
            index += 1
        }
    }
    return (max(1, sampleRate), max(1, pointsPerSecond), duration)
}

func parseTimelineColumnOptions(_ args: [String]) -> (width: Int, totalDuration: Double, vadSegments: [TimelineRange]) {
    var width = 0
    var totalDuration = 0.0
    var vadJSON = "[]"
    var index = 0
    while index < args.count {
        let key = args[index]
        let value = index + 1 < args.count ? args[index + 1] : ""
        switch key {
        case "--width":
            width = Int(value) ?? width
            index += 2
        case "--total":
            totalDuration = Double(value) ?? totalDuration
            index += 2
        case "--vad-json":
            vadJSON = value
            index += 2
        default:
            index += 1
        }
    }
    let data = Data(vadJSON.utf8)
    let vadSegments = (try? JSONDecoder().decode([TimelineRange].self, from: data)) ?? []
    return (max(0, width), max(0, totalDuration), vadSegments)
}

do {
    try run()
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
    FileHandle.standardError.write(Data("error: \(message)\n".utf8))
    exit(1)
}
