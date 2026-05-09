import Foundation
import WhisperKit

struct WorkerRequest: Decodable {
    let op: String?
    let taskId: String
    let chunkPaths: [String]
    let model: String
    let language: String
    let wordTimestamps: Bool

    enum CodingKeys: String, CodingKey {
        case op
        case taskId = "task_id"
        case chunkPaths = "chunk_paths"
        case model
        case language
        case wordTimestamps = "word_timestamps"
    }
}

struct WorkerResponse: Encodable {
    let backend: String?
    let taskId: String
    let index: Int?
    let result: TranscriptionPayload?
    let loadedModel: String?
    let wordTimestamps: Bool?
    let done: Bool?
    let error: String?
    let stage: String?

    enum CodingKeys: String, CodingKey {
        case backend
        case taskId = "task_id"
        case index
        case result
        case loadedModel = "loaded_model"
        case wordTimestamps = "word_timestamps"
        case done
        case error
        case stage
    }
}

struct TranscriptionPayload: Encodable {
    let backend: String
    let loadedModel: String
    let segments: [SegmentPayload]
    let text: String
    let wordTimestamps: Bool

    enum CodingKeys: String, CodingKey {
        case backend
        case loadedModel = "loaded_model"
        case segments
        case text
        case wordTimestamps = "word_timestamps"
    }
}

struct SegmentPayload: Encodable {
    let start: Double
    let end: Double
    let text: String
    let words: [WordPayload]
}

struct WordPayload: Encodable {
    let word: String
    let start: Double
    let end: Double
    let confidence: Double?
}

@MainActor
final class ModelCache {
    private var cachedModel: String = ""
    private var whisperKit: WhisperKit?

    func model(named model: String) async throws -> WhisperKit {
        if let existing = whisperKit, cachedModel == model {
            return existing
        }
        let kit = try await WhisperKit(model: model)
        whisperKit = kit
        cachedModel = model
        return kit
    }
}

let encoder = JSONEncoder()
encoder.outputFormatting = []
let decoder = JSONDecoder()
let cache = ModelCache()

func emit(_ response: WorkerResponse) {
    do {
        let data = try encoder.encode(response)
        if let line = String(data: data, encoding: .utf8) {
            FileHandle.standardOutput.write(Data((line + "\n").utf8))
        }
    } catch {
        let fallback = #"{"task_id":"","error":"encode_failed","stage":"emit"}"#
        FileHandle.standardOutput.write(Data((fallback + "\n").utf8))
    }
}

func emitError(taskId: String, index: Int? = nil, error: Error, stage: String) {
    emit(
        WorkerResponse(
            backend: nil,
            taskId: taskId,
            index: index,
            result: nil,
            loadedModel: nil,
            wordTimestamps: nil,
            done: nil,
            error: String(describing: error),
            stage: stage
        )
    )
}

func segmentPayloads(from results: [TranscriptionResult], includeWords: Bool) -> [SegmentPayload] {
    var rows: [SegmentPayload] = []
    for result in results {
        for segment in result.segments {
            let words: [WordPayload]
            if includeWords {
                words = (segment.words ?? []).map { item in
                    WordPayload(
                        word: item.word.trimmingCharacters(in: .whitespacesAndNewlines),
                        start: Double(item.start),
                        end: Double(item.end),
                        confidence: Double(item.probability)
                    )
                }.filter { !$0.word.isEmpty && $0.end >= $0.start }
            } else {
                words = []
            }
            let text = segment.text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                rows.append(
                    SegmentPayload(
                        start: Double(segment.start),
                        end: max(Double(segment.start), Double(segment.end)),
                        text: text,
                        words: words
                    )
                )
            }
        }
    }
    if rows.isEmpty {
        let text = results.map { $0.text }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            rows.append(SegmentPayload(start: 0.0, end: 0.0, text: text, words: []))
        }
    }
    return rows
}

@MainActor
func handle(_ request: WorkerRequest) async {
    do {
        let kit = try await cache.model(named: request.model)
        let options = DecodingOptions(
            verbose: false,
            task: .transcribe,
            language: request.language,
            wordTimestamps: request.wordTimestamps
        )
        for (index, path) in request.chunkPaths.enumerated() {
            do {
                let results = try await kit.transcribe(audioPath: path, decodeOptions: options)
                let payload = TranscriptionPayload(
                    backend: "whisperkit-persistent",
                    loadedModel: request.model,
                    segments: segmentPayloads(from: results, includeWords: request.wordTimestamps),
                    text: results.map { $0.text }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines),
                    wordTimestamps: request.wordTimestamps
                )
                emit(
                    WorkerResponse(
                        backend: "whisperkit-persistent",
                        taskId: request.taskId,
                        index: index,
                        result: payload,
                        loadedModel: request.model,
                        wordTimestamps: request.wordTimestamps,
                        done: nil,
                        error: nil,
                        stage: nil
                    )
                )
            } catch {
                emitError(taskId: request.taskId, index: index, error: error, stage: "transcribe")
            }
        }
        emit(
            WorkerResponse(
                backend: nil,
                taskId: request.taskId,
                index: nil,
                result: nil,
                loadedModel: nil,
                wordTimestamps: request.wordTimestamps,
                done: true,
                error: nil,
                stage: nil
            )
        )
    } catch {
        emitError(taskId: request.taskId, error: error, stage: "model_load")
    }
}

while let line = readLine(strippingNewline: true) {
    guard !line.isEmpty else {
        continue
    }
    guard let data = line.data(using: .utf8) else {
        emitError(taskId: "", error: NSError(domain: "worker", code: 1), stage: "input_encoding")
        continue
    }
    do {
        let request = try decoder.decode(WorkerRequest.self, from: data)
        if request.op == "quit" {
            break
        }
        await handle(request)
    } catch {
        emitError(taskId: "", error: error, stage: "request_decode")
    }
}
