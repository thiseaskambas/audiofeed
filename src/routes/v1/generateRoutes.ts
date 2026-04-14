import { Router } from 'express';
import path from 'path';

import generateController from '../../controllers/v1/generateController';
import apiKeyMiddleware from '../../middleware/apiKeyMiddleware';

const router = Router();

router.get('/health', generateController.health);

router.get('/openapi.yaml', (_req, res) => {
  res.setHeader('Content-Type', 'application/yaml');
  res.sendFile(path.join(process.cwd(), 'openapi.yaml'));
});

router.get('/docs', (_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.send(`<!DOCTYPE html>
<html>
<head>
  <title>Audiofeed API</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script>
<script>
  SwaggerUIBundle({ url: '/openapi.yaml', dom_id: '#swagger-ui', presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset] });
</script>
</body>
</html>`);
});
router.post('/generate', apiKeyMiddleware.protect, generateController.generate);
router.get(
  '/jobs/:jobId',
  apiKeyMiddleware.protect,
  generateController.getJobStatus
);

export default router;
