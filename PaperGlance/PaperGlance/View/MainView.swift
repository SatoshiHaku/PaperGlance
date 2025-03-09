//
//  MainView.swift
//  PaperGlance
//
//  Created by Satoshi Haku on 2025/03/09.
//

import SwiftUI

struct MainView: View {
    @StateObject var viewModel = MainViewModel()
    @State private var showDocumentPicker = false
    @State private var selectedFileURL: URL?

    var body: some View {
        VStack {
            if viewModel.isProcessing {
                ProgressView("処理中...")
            } else {
                Button("PDFを選択") {
                    showDocumentPicker.toggle()
                }
                if let translatedText = viewModel.translatedMarkdown, !translatedText.isEmpty {
                    ScrollView {
                        Text(translatedText)
                            .padding()
                    }
                }
            }
        }
        .sheet(isPresented: $showDocumentPicker) {
            DocumentPicker { url in
                selectedFileURL = url
                if let url = selectedFileURL {
                    viewModel.processPDF(fileURL: url)
                }
            }
        }
    }
}

#Preview {
    MainView()
}


