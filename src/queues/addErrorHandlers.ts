import { Job, Worker } from 'bullmq';
import path from 'path';
import winston from 'winston';
import DailyRotateFile from 'winston-daily-rotate-file';

import { AppError } from '../utils/appError';

const logDirectory = path.join(__dirname, '../../logs');

const queueErrorLogger = winston.createLogger({
  transports: [
    new winston.transports.Console(),
    new DailyRotateFile({
      filename: path.join(logDirectory, 'errors-%DATE%.log'),
      datePattern: 'YYYY-MM-DD',
      maxFiles: '3d',
    }),
  ],
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
});

export const addWorkerErrorHandler = (worker: Worker, workerName: string) => {
  worker.on('error', (err) => {
    if (
      err.message.includes('ENOTFOUND') ||
      err.message.includes('ECONNREFUSED') ||
      err.message.includes('EADDRNOTAVAIL')
    ) {
      return;
    }
    queueErrorLogger.error(`${workerName} connection error:`, {
      error: err.message,
      stack: err.stack,
      workerName,
    });
  });

  worker.on('failed', (job: Job | undefined, err: Error) => {
    queueErrorLogger.error(`${workerName} job failed`, {
      jobId: job?.id,
      jobData: job?.data,
      error: err.message,
      stack: err.stack,
      additionalInfo: err instanceof AppError ? err.additionalInfo : undefined,
      workerName,
    });
  });
};
