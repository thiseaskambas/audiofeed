import { ErrorStatusCode } from '../tsTypes';

interface AppErrorArgs {
  message: string;
  name?: string;
  statusCode?: ErrorStatusCode;
  status?: string;
  additionalInfo?: string;
  isOperational?: boolean;
}

export class AppError extends Error {
  public statusCode: ErrorStatusCode;
  public message: string;
  public status: string;
  public additionalInfo: string;
  public isOperational = true;

  constructor(args: AppErrorArgs) {
    super(args.message);

    Object.setPrototypeOf(this, new.target.prototype);

    this.statusCode = args.statusCode || ErrorStatusCode.INTERNAL_SERVER_ERROR;
    this.status = `${this.statusCode}`.startsWith('4') ? 'Fail' : 'Error';
    this.message = args.message || 'Something went VERY wrong';
    this.additionalInfo = args.additionalInfo || '';
    this.isOperational = args.isOperational ?? true;
    Error.captureStackTrace(this);
  }
}
