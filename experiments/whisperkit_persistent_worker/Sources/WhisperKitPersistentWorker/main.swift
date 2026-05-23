import Foundation
import CoreML
import WhisperKit

struct WorkerRequest: Decodable {
    let op: String?
    let taskId: String
    let chunkPaths: [String]
    let model: String
    let language: String
    let wordTimestamps: Bool
    let concurrentWorkerCount: Int?
    let streamResults: Bool?
    let computeProfile: String?

    enum CodingKeys: String, CodingKey {
        case op
        case taskId = "task_id"
        case chunkPaths = "chunk_paths"
        case model
        case language
        case wordTimestamps = "word_timestamps"
        case concurrentWorkerCount = "concurrent_worker_count"
        case streamResults = "stream_results"
        case computeProfile = "compute_profile"
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
    private var cachedKey: String = ""
    private var whisperKit: WhisperKit?

    func model(named model: String, computeProfile: String?) async throws -> WhisperKit {
        let profile = normalizedComputeProfile(computeProfile)
        let cacheKey = "\(model)|\(profile)"
        if let existing = whisperKit, cachedKey == cacheKey {
            return existing
        }
        let config = WhisperKitConfig(
            model: model,
            computeOptions: computeOptions(for: profile),
            verbose: false,
            prewarm: false
        )
        let kit = try await WhisperKit(config)
        whisperKit = kit
        cachedKey = cacheKey
        return kit
    }
}

let encoder = JSONEncoder()
encoder.outputFormatting = []
let decoder = JSONDecoder()
let cache = ModelCache()
let newlineData = Data([0x0A])

func emit(_ response: WorkerResponse) {
    do {
        let data = try encoder.encode(response)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(newlineData)
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

@MainActor
func handle(_ request: WorkerRequest) async {
    do {
        let kit = try await cache.model(named: request.model, computeProfile: request.computeProfile)
        let workerCount = max(1, request.concurrentWorkerCount ?? 1)
        if request.streamResults == true {
            await transcribeStreamingRollingPool(kit: kit, request: request, workerCount: workerCount)
        } else {
            let options = decodeOptions(
                language: request.language,
                wordTimestamps: request.wordTimestamps,
                workerCount: workerCount
            )
            let batchSize = max(1, min(workerCount, max(1, request.chunkPaths.count)))
            var batchStart = 0
            while batchStart < request.chunkPaths.count {
                let batchEnd = min(request.chunkPaths.count, batchStart + batchSize)
                let batchPaths = Array(request.chunkPaths[batchStart..<batchEnd])
                let batchResults = await kit.transcribeWithResults(audioPaths: batchPaths, decodeOptions: options)
                for (offset, result) in batchResults.enumerated() {
                    emitTranscribeResult(
                        taskId: request.taskId,
                        index: batchStart + offset,
                        result: result,
                        loadedModel: request.model,
                        wordTimestamps: request.wordTimestamps
                    )
                }
                batchStart = batchEnd
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
