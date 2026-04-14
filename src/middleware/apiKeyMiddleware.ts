import { NextFunction, Request, Response } from 'express';

import { ErrorStatusCode } from '../tsTypes';
import { AppError } from '../utils/appError';
import config from '../utils/config';

const protect = (req: Request, _res: Response, next: NextFunction): void => {
  const apiKey = req.headers['x-api-key'];
  if (!apiKey || typeof apiKey !== 'string' || apiKey !== config.API_SECRET) {
    throw new AppError({
      message: 'Invalid or missing X-API-Key',
      statusCode: ErrorStatusCode.UNAUTHORIZED,
    });
  }
  next();
};

export default { protect };
