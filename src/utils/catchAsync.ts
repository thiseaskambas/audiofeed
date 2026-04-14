import express from 'express';

type AsyncFunction = (
  req: express.Request,
  res: express.Response,
  next: express.NextFunction
) => Promise<void>;

export const catchAsync = (fn: AsyncFunction) => {
  return (
    req: express.Request,
    res: express.Response,
    next: express.NextFunction
  ) => {
    return fn(req, res, next).catch(next);
  };
};
