import SwiftUI

public struct LoginView: View {
    @ObservedObject var authVM: AuthViewModel
    var onNavigateToRegister: () -> Void
    
    @State private var email: String = ""
    @State private var password: String = ""
    
    public init(authVM: AuthViewModel, onNavigateToRegister: @escaping () -> Void) {
        self.authVM = authVM
        self.onNavigateToRegister = onNavigateToRegister
    }
    
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    Spacer(minLength: 40)
                    
                    // Brand Header
                    VStack(spacing: 8) {
                        Text("Provision")
                            .font(.system(size: 34, weight: .bold, design: .serif))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                        
                        Text("Household food, under control.")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    .padding(.bottom, 12)
                    
                    // Error Message Banner
                    if let err = authVM.errorMessage {
                        HStack(spacing: 10) {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundStyle(ProvisionTheme.redAlert)
                            Text(err)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(ProvisionTheme.redAlert)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(ProvisionTheme.redLight)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    
                    // Form Fields Card
                    VStack(alignment: .leading, spacing: 18) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Email")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            HStack(spacing: 10) {
                                Image(systemName: "envelope.fill")
                                    .font(.system(size: 14))
                                    .foregroundStyle(ProvisionTheme.textTertiary)
                                    .frame(width: 20)
                                TextField("name@example.com", text: $email)
                                    .keyboardType(.emailAddress)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .tint(ProvisionTheme.provisionGreen)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(ProvisionTheme.inputBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .stroke(ProvisionTheme.border, lineWidth: 1)
                            )
                        }
                        
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Password")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            HStack(spacing: 10) {
                                Image(systemName: "lock.fill")
                                    .font(.system(size: 14))
                                    .foregroundStyle(ProvisionTheme.textTertiary)
                                    .frame(width: 20)
                                SecureField("Enter password", text: $password)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .tint(ProvisionTheme.provisionGreen)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(ProvisionTheme.inputBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .stroke(ProvisionTheme.border, lineWidth: 1)
                            )
                        }
                        
                        // Submit Button
                        Button {
                            Task {
                                _ = await authVM.login(email: email, password: password)
                            }
                        } label: {
                            HStack {
                                if authVM.isLoading {
                                    ProgressView()
                                        .tint(.white)
                                } else {
                                    Text("Sign In")
                                        .font(.system(size: 16, weight: .bold))
                                }
                            }
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .background(isSubmitDisabled ? ProvisionTheme.provisionGreen.opacity(0.4) : ProvisionTheme.provisionGreen)
                            .foregroundStyle(ProvisionTheme.onAccent)
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                        .disabled(isSubmitDisabled || authVM.isLoading)
                        .padding(.top, 6)
                    }
                    .padding(20)
                    .provisionCard()
                    
                    // Navigation to Register
                    Button {
                        onNavigateToRegister()
                    } label: {
                        HStack(spacing: 4) {
                            Text("Don't have an account?")
                                .foregroundStyle(ProvisionTheme.textSecondary)
                            Text("Create Account")
                                .fontWeight(.bold)
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .font(.system(size: 14))
                        .padding(.vertical, 8)
                        .accessibleTouchTarget()
                    }
                    .padding(.top, 8)
                    
                    Spacer()
                }
                .padding(.horizontal, 20)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(ProvisionTheme.background.ignoresSafeArea())
        }
    }
    
    private var isSubmitDisabled: Bool {
        email.trimmingCharacters(in: .whitespaces).isEmpty || password.isEmpty
    }
}
