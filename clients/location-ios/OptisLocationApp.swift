import SwiftUI
import UIKit

@main
struct OptisLocationApp: App {
    var body: some Scene {
        WindowGroup { LocationView() }
    }
}

private struct LocationView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var endpoint = ""
    @State private var token = ""
    @State private var status = "Idle"
    @State private var sender: PhoneLocation?

    var body: some View {
        Form {
            TextField("Optis server URL", text: $endpoint)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .disabled(sender != nil)
            SecureField("Local Optis token", text: $token)
                .disabled(sender != nil)
            Button(sender == nil ? "Start sending location" : "Stop sending location") {
                if let sender {
                    sender.stop()
                    self.sender = nil
                    status = "Stopped"
                    return
                }
                let trimmedToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
                guard var address = URLComponents(string: endpoint.trimmingCharacters(in: .whitespacesAndNewlines)),
                      ["http", "https"].contains(address.scheme ?? ""),
                      let host = address.host, !host.isEmpty, address.user == nil, address.password == nil,
                      address.query == nil, address.fragment == nil,
                      ["", "/", "/v1/location"].contains(address.path), !trimmedToken.isEmpty else {
                    status = "Enter the Optis server URL and the location token."
                    return
                }
                address.path = "/v1/location"
                guard let url = address.url else {
                    status = "That Optis server URL is invalid."
                    return
                }
                let sender = PhoneLocation(endpoint: url, token: trimmedToken) { status = $0 }
                self.sender = sender
                status = "Waiting for a location fix."
                sender.start()
            }
            Text(status)
            Text("Keep Optis Location open while walking.")
                .foregroundStyle(.secondary)
        }
        .onChange(of: sender != nil) { _, isSending in
            UIApplication.shared.isIdleTimerDisabled = isSending
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background, let sender {
                sender.stop()
                self.sender = nil
                status = "Stopped when the app left the foreground."
            }
        }
        .onDisappear {
            UIApplication.shared.isIdleTimerDisabled = false
            sender?.stop()
            sender = nil
        }
    }
}
