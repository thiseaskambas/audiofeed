import axios from 'axios';

import logger from '../../utils/logger';

const fireWebhook = async (
  webhookUrl: string,
  payload: Record<string, unknown>
): Promise<void> => {
  try {
    await axios.post(webhookUrl, payload, { timeout: 30_000 });
  } catch (err) {
    logger.warn('Webhook POST failed', {
      webhookUrl,
      err: err instanceof Error ? err.message : err,
    });
  }
};

export default { fireWebhook };
