import SwiftUI

public struct RegisterView: View {
    @ObservedObject var authVM: AuthViewModel
    var onNavigateToLogin: () -> Void
    
    @State private var displayName: String = ""
    @State private var email: String = ""
    @State private var password: String = ""
    @State private var confirmPassword: String = ""
    @State private var validationError: String? = nil
    
    public init(authVM: AuthViewModel, onNavigateToLogin: @escaping () -> Void) {
        self.authVM = authVM
        self.onNavigateToLogin = onNavigateToLogin
    }
    
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    Spacer(minLength: 20)
                    
                    // Header
                    VStack(spacing: 6) {
                        Text("Create Account")
                            .font(.system(size: 30, weight: .bold, design: .serif))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        
                        Text("Join your household pantry on Provision")
                            .font(.system(size: 14))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    .padding(.bottom, 8)
                    
                    // Error Banner (Validation or Backend error)
                    if let err = validationError ?? authVM.errorMessage {
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
                    
                    // Registration Card
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Your Name (Optional)")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            TextField("e.g. Alex", text: $displayName)
                                .padding(14)
                                .background(ProvisionTheme.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
                        }
                        
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Email")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            TextField("name@example.com", text: $email)
                                .keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .padding(14)
                                .background(ProvisionTheme.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
                        }
                        
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Password (min 6 characters)")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            SecureField("Enter password", text: $password)
                                .padding(14)
                                .background(ProvisionTheme.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
                        }
                        
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Confirm Password")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .tracking(0.6)
                            
                            SecureField("Re-enter password", text: $confirmPassword)
                                .padding(14)
                                .background(ProvisionTheme.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
                        }
                        
                        // Submit Button
                        Button {
                            validateAndSubmit()
                        } label: {
                            HStack {
                                if authVM.isLoading {
                                    ProgressView()
                                        .tint(.white)
                                } else {
                                    Text("Create Account")
                                        .font(.system(size: 16, weight: .bold))
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(isSubmitDisabled ? ProvisionTheme.provisionGreen.opacity(0.5) : ProvisionTheme.provisionGreen)
                            .foregroundStyle(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(isSubmitDisabled || authVM.isLoading)
                        .padding(.top, 6)
                    }
                    .padding(20)
                    .provisionCard()
                    
                    // Switch to Sign In
                    Button {
                        onNavigateToLogin()
                    } label: {
                        HStack(spacing: 4) {
                            Text("Already have an account?")
                                .foregroundStyle(ProvisionTheme.textSecondary)
                            Text("Sign In")
                                .fontWeight(.bold)
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .font(.system(size: 14))
                    }
                    .padding(.top, 4)
                    
                    Spacer()
                }
                .padding(.horizontal, 20)
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
        }
    }
    
    private var isSubmitDisabled: Bool {
        email.trimmingCharacters(in: .whitespaces).isEmpty || password.isEmpty || confirmPassword.isEmpty
    }
    
    private func validateAndSubmit() {
        validationError = nil
        
        let trimmedEmail = email.trimmingCharacters(in: .whitespaces)
        guard trimmedEmail.contains("@") && trimmedEmail.contains(".") else {
            validationError = "Please enter a valid email address."
            return
        }
        
        guard password.count >= 6 else {
            validationError = "Password must be at least 6 characters."
            return
        }
        
        guard password == confirmPassword else {
            validationError = "Passwords do not match."
            return
        }
        
        Task {
            _ = await authVM.register(
                email: trimmedEmail,
                password: password,
                displayName: displayName.isEmpty ? nil : displayName
            )
        }
    }
}
