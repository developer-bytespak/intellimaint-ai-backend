export interface IApiResponse {
    statusCode: number;
    message: string;
    data?: any;  // Optional data field
  }
  
  export interface IApiError {
    statusCode: number;
    message: string;
    errorDetails?: string;  // Optional details about the error
  }
  