import express, { Express } from 'express';
import helmet from 'helmet';

import errorController from './controllers/v1/errorController';
import v1Router from './routes/v1';
import { errorLogger, requestLogger } from './utils/logger';

const app: Express = express();

app.use(requestLogger);
app.set('trust proxy', 1);
app.use(helmet());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

app.use('/', v1Router);

app.use(errorLogger);
app.use(errorController.errorHandler);

export { app };
