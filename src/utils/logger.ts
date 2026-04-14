import expressWinston from 'express-winston';
import path from 'path';
import winston from 'winston';
import DailyRotateFile from 'winston-daily-rotate-file';

import config from './config';

const logDirectory = path.join(__dirname, '../../logs');
const isSilent = config.LOG_LEVEL === 'silent';
const isDev = config.ENV === 'DEV';

const fileTransport = (filename: string) =>
  new DailyRotateFile({
    filename: path.join(logDirectory, filename),
    datePattern: 'YYYY-MM-DD',
    maxFiles: '3d',
  });

const jsonFormat = winston.format.combine(
  winston.format.timestamp(),
  winston.format.errors({ stack: true }),
  winston.format.json()
);

const devConsoleFormat = winston.format.combine(
  winston.format.colorize(),
  winston.format.timestamp({ format: 'HH:mm:ss' }),
  winston.format.printf(({ level, message, timestamp, ...meta }) => {
    const metaStr =
      Object.keys(meta).length > 0 ? ` ${JSON.stringify(meta)}` : '';
    return `${timestamp} ${level}: ${message}${metaStr}`;
  })
);

const consoleFormat = isDev ? devConsoleFormat : jsonFormat;

const logger = winston.createLogger({
  silent: isSilent,
  level:
    config.LOG_LEVEL && config.LOG_LEVEL !== 'silent'
      ? config.LOG_LEVEL
      : undefined,
  transports: [
    new winston.transports.Console({
      silent: isSilent,
      format: consoleFormat,
    }),
    ...(isSilent ? [] : [fileTransport('errors-%DATE%.log')]),
  ],
  format: jsonFormat,
});

export default logger;

export const requestLogger = expressWinston.logger({
  transports: [
    new winston.transports.Console({ silent: isSilent }),
    ...(isSilent ? [] : [fileTransport('requests-%DATE%.log')]),
  ],
  format: winston.format.combine(
    winston.format.colorize(),
    winston.format.json()
  ),
  meta: true,
  msg: 'HTTP {{req.method}} {{req.url}}',
  expressFormat: true,
  colorize: false,
});

export const errorLogger = expressWinston.errorLogger({
  transports: [
    new winston.transports.Console({ silent: isSilent }),
    ...(isSilent ? [] : [fileTransport('errors-%DATE%.log')]),
  ],
  format: winston.format.combine(
    winston.format.colorize(),
    winston.format.json()
  ),
});
