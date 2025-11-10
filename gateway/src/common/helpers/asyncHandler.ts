import { nestError } from './responseHelpers';  

const asyncHandler = (fn: Function) => {
  return async (req: any, res: any) => {
    try {
      await fn(req, res);  
    } catch (error) {
      console.error('Error:', error); 
      return nestError(500, 'Something went wrong', error.message)(res);  
    }
  };
};

export { asyncHandler };
