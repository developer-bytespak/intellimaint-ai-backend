import { Response } from 'express';
import { IApiResponse } from '../types/apiResponseTypes';

function safeSerialize(obj: any) {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj !== 'object') return obj;

  const seen = new WeakSet();
  try {
    const str = JSON.stringify(obj, function (_key, value) {
      if (typeof value === 'object' && value !== null) {
        if (seen.has(value)) return '[Circular]';
        seen.add(value);
      }
      return value;
    });
    return JSON.parse(str);
  } catch (e) {
    return { _unsafe: String(obj) };
  }
}

const nestResponse = (statusCode: number, message: string, data: any = null) => {
  return (res: Response) => {
    const safeData = safeSerialize(data);
    return res.status(statusCode).json({
      statusCode,
      message,
      data: safeData,
    });
  };
};

const nestError = (statusCode: number, message: string, data: any = null) => {
  return (res: Response) => {
    const safeData = safeSerialize(data);
    return res.status(statusCode).json({
      statusCode,
      message,
      data: safeData,
    });
  };
};

export { nestResponse, nestError };
