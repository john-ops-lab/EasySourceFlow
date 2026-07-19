#!/usr/bin/env swift

import AppKit
import Foundation
import PDFKit
import Vision

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("Usage: macos_pdf_ocr.swift <pdf-path>\n".utf8))
    exit(2)
}

let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let document = PDFDocument(url: sourceURL) else {
    FileHandle.standardError.write(Data("Could not open PDF.\n".utf8))
    exit(1)
}

func recognizedText(for page: PDFPage) throws -> String {
    if let embedded = page.string?.trimmingCharacters(in: .whitespacesAndNewlines), !embedded.isEmpty {
        return embedded
    }

    let bounds = page.bounds(for: .mediaBox)
    let target = NSSize(width: max(1600, bounds.width * 2.5), height: max(2200, bounds.height * 2.5))
    let image = page.thumbnail(of: target, for: .mediaBox)
    var proposedRect = NSRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) else {
        return ""
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])

    let observations = (request.results ?? []).sorted { left, right in
        let verticalDistance = abs(left.boundingBox.midY - right.boundingBox.midY)
        if verticalDistance > 0.015 {
            return left.boundingBox.midY > right.boundingBox.midY
        }
        return left.boundingBox.minX < right.boundingBox.minX
    }
    return observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

var extractedPages = 0
for index in 0..<document.pageCount {
    autoreleasepool {
        guard let page = document.page(at: index) else { return }
        do {
            let text = try recognizedText(for: page).trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                extractedPages += 1
                print("[Page \(index + 1)]")
                print(text)
                print("")
            }
        } catch {
            FileHandle.standardError.write(Data("OCR failed on page \(index + 1): \(error)\n".utf8))
        }
    }
}

if extractedPages == 0 {
    FileHandle.standardError.write(Data("No text could be extracted from the PDF.\n".utf8))
    exit(1)
}
