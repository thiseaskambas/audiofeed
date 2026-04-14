import { NextFunction, Request, Response } from 'express';

import { ErrorStatusCode } from '../../tsTypes';
import { AppError } from '../../utils/appError';
import config from '../../utils/config';

const errorHandler = (
  err: Error | AppError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void => {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({ detail: err.message });
    return;
  }
  if (config.ENV === 'DEV') {
    res
      .status(ErrorStatusCode.INTERNAL_SERVER_ERROR)
      .json({ detail: err.message, stack: err.stack });
    return;
  }
  res
    .status(ErrorStatusCode.INTERNAL_SERVER_ERROR)
    .json({ detail: 'An unexpected error occurred' });
};

export default { errorHandler };
