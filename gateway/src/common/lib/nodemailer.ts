import { appConfig } from 'src/config/app.config'; 
import { Verification_Email_Template } from './Email_Template';
import sgMail from '@sendgrid/mail';

// Initialize SendGrid
sgMail.setApiKey(appConfig.sendgrid.apiKey);

async function sendEmailOTP(mail: string, otp: string) {
    const mailOptions = {
        from: appConfig.sendgrid.fromEmail,
        to: mail,
        subject: "OTP Verification",
        html: Verification_Email_Template(otp),
    };

    try {
        const response = await sgMail.send(mailOptions);
        console.log('SendGrid response:', response);
        return {
            success: true,
            message: `OTP sent to ${mail} via email`,
        };
    } catch (error: any) {
        console.error('SendGrid error:', error.message);
        console.error('SendGrid error response:', error.response?.body);
        return {
            success: false,
            message: `Error sending OTP to ${mail} via email: ${error.message}`,
        };
    }
}

export { sendEmailOTP }
