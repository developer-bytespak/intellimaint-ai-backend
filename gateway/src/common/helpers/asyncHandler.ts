import { nestError } from './responseHelpers';  

const asyncHandler = (fn: Function) => {
  return async (req: any, res: any) => {
    try {
      await fn(req, res);  
    } catch (error: unknown) {
      console.error('Error:', error); 
      const err = error as { message?: string };
      return nestError(500, 'Something went wrong', err.message || 'Internal server error')(res);  
    }
  };
};

export { asyncHandler };
