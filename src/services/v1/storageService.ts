import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import fs from 'fs';
import path from 'path';

import config from '../../utils/config';
import { AUDIO_S3_PREFIX } from '../../utils/constants';

const s3 = new S3Client({
  credentials: {
    accessKeyId: config.S3_ACCESS_KEY_ID,
    secretAccessKey: config.S3_SECRET_ACCESS_KEY,
  },
  endpoint: config.S3_ENDPOINT_URL,
  forcePathStyle: true, // Required for Sevalla/Cloudflare R2
  region: 'auto',
});

const uploadAudio = async (
  localPath: string,
  keyPrefix: string,
  filename?: string
): Promise<string> => {
  const name = filename ?? path.basename(localPath);
  const key = `${AUDIO_S3_PREFIX}/${keyPrefix}/${name}`;
  const body = fs.createReadStream(localPath);

  await s3.send(
    new PutObjectCommand({
      Bucket: config.S3_BUCKET_NAME,
      Key: key,
      Body: body,
      ContentType: 'audio/mpeg',
    })
  );

  const base = (config.S3_PUBLIC_URL || config.S3_ENDPOINT_URL).replace(
    /\/$/,
    ''
  );
  return `${base}/${key}`;
};

export default { uploadAudio };
