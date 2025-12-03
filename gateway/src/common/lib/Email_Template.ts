export const Verification_Email_Template = (code: string) => `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Email Verification - Uni-Connect</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 500px;
            margin: 40px auto;
            background: #ffffff;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 1px solid #e1e5e9;
        }
        .header {
            background: linear(135deg, #667eea 0%, #764ba2 100%);
            color: #ffffff;
            padding: 20px;
            font-size: 24px;
            font-weight: bold;
            border-radius: 8px;
            margin-bottom: 25px;
        }
        .logo {
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }
        .code {
            font-size: 32px;
            margin: 30px 0;
            background: #f8f9fa;
            padding: 15px 30px;
            display: inline-block;
            border-radius: 8px;
            letter-spacing: 6px;
            font-weight: bold;
            color: #2d3748;
            border: 2px dashed #cbd5e0;
        }
        .message {
            color: #4a5568;
            font-size: 16px;
            line-height: 1.6;
            margin: 20px 0;
        }
        .expiry-note {
            color: #e53e3e;
            font-weight: bold;
            font-size: 14px;
            margin: 15px 0;
        }
        .footer {
            font-size: 12px;
            color: #718096;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
        }
        .support {
            color: #667eea;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Uni-Connect</div>
        <div class="header">Verify Your Email Address</div>
        
        <p class="message">
            Welcome to Uni-Connect! We're excited to have you join our academic community. 
            To complete your registration and start connecting with fellow students and educators, 
            please verify your email address using the code below:
        </p>
        
        <div class="code">${code}</div>
        
        <p class="expiry-note">This verification code will expire in 5 minutes for security reasons.</p>
        
        <p class="message">
            If you didn't create an account with Uni-Connect, please ignore this email. 
            This verification code can only be used once.
        </p>
        
        <div class="footer">
            &copy; ${new Date().getFullYear()} Uni-Connect. All rights reserved.<br>
            Connecting Students, Building Futures.<br>
            Need help? Contact us at <a href="mailto:support@uni-connect.com" class="support">support@uni-connect.com</a>
        </div>
    </div>
</body>
</html>`;

export const SEND_EMAIL_LINK = (link: string, subject: string) => `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${subject} - Uni-Connect</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            color: #2d3748;
            margin: 0;
            padding: 0;
        }
        .email-container {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 1px solid #e1e5e9;
        }
        .email-header {
            text-align: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e2e8f0;
        }
        .logo {
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 15px;
        }
        .email-header h2 {
            color: #2d3748;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .email-body p {
            color: #4a5568;
            line-height: 1.6;
            font-size: 16px;
        }
        .email-button {
            text-align: center;
            margin: 30px 0;
        }
        .email-button a {
            display: inline-block;
            padding: 16px 32px;
            font-size: 18px;
            font-weight: bold;
            color: #ffffff;
            background: linear(135deg, #667eea 0%, #764ba2 100%);
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
        }
        .email-button a:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
        }
        .email-footer {
            text-align: center;
            font-size: 12px;
            color: #718096;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
        }
        .email-footer a {
            color: #667eea;
            text-decoration: none;
        }
        .security-note {
            background: #fffaf0;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #dd6b20;
            margin: 20px 0;
            font-size: 14px;
        }
        .instruction {
            background: #f0fff4;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #38a169;
            margin: 20px 0;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-header">
            <div class="logo">Uni-Connect</div>
            <h2>${subject}</h2>
            <p>
                ${subject === "Reset Password"
    ? "Securely reset your password to regain access to your Uni-Connect account and continue your academic journey."
    : "Welcome to Uni-Connect! Create your account and join our vibrant academic community."}
            </p>
        </div>
        
        <div class="email-body">
            <p>Hello,</p>
            <p>
                ${subject === "Reset Password"
    ? "We received a request to reset your password for your Uni-Connect account. To proceed with securing your account, please click the button below:"
    : "You're one step away from joining Uni-Connect! To complete your account creation and start connecting with students and educators, please click the button below:"}
            </p>
            
            <div class="instruction">
                <strong>Important:</strong> This link is valid for <strong>8 minutes</strong> for security purposes. 
                ${subject === "Reset Password"
    ? "After resetting, you'll be able to log in with your new password immediately."
    : "After verification, you'll gain full access to all Uni-Connect features."}
            </div>
        </div>
        
        <div class="email-button">
            <a href="${link}" target="_blank">
                ${subject === "Reset Password" ? "Reset Your Password" : "Create Your Account"}
            </a>
        </div>
        
        <div class="security-note">
            <strong>Security Notice:</strong> If you didn't request this ${subject === "Reset Password" ? "password reset" : "account creation"}, 
            please ignore this email. Your account security is important to us.
        </div>
        
        <div class="email-body">
            <p>
                ${subject === "Reset Password"
    ? "Once reset, you can use your new password to access all Uni-Connect features including course discussions, study groups, and academic resources."
    : "With Uni-Connect, you'll be able to join study groups, participate in course discussions, share resources, and connect with peers and mentors."}
            </p>
            <p>
                Best regards,<br>
                <strong>The Uni-Connect Team</strong><br>
                <em>Connecting Students, Building Futures</em>
            </p>
        </div>
        
        <hr>
        
        <div class="email-footer">
            <p>
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="${link}" target="_blank">${link}</a>
            </p>
            <p>
                Need assistance? Contact our support team at 
                <a href="mailto:support@uni-connect.com">support@uni-connect.com</a>
            </p>
            <p>&copy; ${new Date().getFullYear()} Uni-Connect. All rights reserved.</p>
        </div>
    </div>
</body>
</html>`;