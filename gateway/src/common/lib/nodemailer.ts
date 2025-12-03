import { appConfig } from 'src/config/app.config'; 
import { SEND_EMAIL_LINK, Verification_Email_Template } from './Email_Template';
import nodemailer from 'nodemailer';

const emailConfig = {
    service: "Gmail",
    host: "smtp.gmail.com",
    port: 587,
    secure: true,
    auth: {
        user: appConfig.portalEmail,
        pass: appConfig.portalPassword,
    },
};

async function sendEmailOTP(mail: string, otp: string) {
    const transporter = nodemailer.createTransport(emailConfig);
    const mailOptions = {
        from: appConfig.portalEmail,
        to: mail,
        subject: "OTP Verification",
        html: Verification_Email_Template(otp),
    };

    try {
        await transporter.sendMail(mailOptions);
        return {
            success: true,
            message: `OTP sent to ${mail} via email`,
        };
    } catch (error) {
        return {
            success: false,
            message: `Error sending OTP to ${mail} via email: ${error}`,
        };
    }
}




export { sendEmailOTP }
