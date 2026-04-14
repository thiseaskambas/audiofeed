import { Router } from 'express';

import generateRouter from './generateRoutes';

export default Router().use('/', generateRouter);
