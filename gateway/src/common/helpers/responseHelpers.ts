import { Response } from 'express';
import { IApiResponse } from '../types/apiResponseTypes'; 
const nestResponse = (statusCode: number, message: string, data: any = null) => {
  return (res: Response)=> {
    return res.status(statusCode).json({
      statusCode,
      message,
      data,
    });
  };
};


const nestError = (statusCode: number, message: string, data: any = null) => {
  return (res: Response) => {
    return res.status(statusCode).json({
      statusCode,
      message,
      data,
    });
  };
};

export { nestResponse, nestError };
