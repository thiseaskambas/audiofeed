import ffmpeg from 'fluent-ffmpeg';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

import logger from './logger';

/**
 * Convert raw PCM bytes (24 kHz, 16-bit, mono) to an MP3 file.
 *
 * Equivalent to Python:
 *   AudioSegment(data=pcm_bytes, sample_width=2, frame_rate=24000, channels=1).export(out_path, format="mp3")
 */
export const pcmToMp3 = (pcmBytes: Buffer, outPath: string): Promise<void> => {
  return new Promise((resolve, reject) => {
    const tmpPcm = path.join(os.tmpdir(), `pcm_${uuidv4()}.raw`);
    fs.writeFileSync(tmpPcm, pcmBytes);

    ffmpeg(tmpPcm)
      .inputFormat('s16le') // signed 16-bit little-endian
      .audioFrequency(24000)
      .audioChannels(1)
      .toFormat('mp3')
      .on('error', (err) => {
        fs.unlink(tmpPcm, () => undefined);
        reject(err);
      })
      .on('end', () => {
        fs.unlink(tmpPcm, () => undefined);
        resolve();
      })
      .save(outPath);
  });
};

/**
 * Concatenate multiple PCM byte buffers into one MP3.
 * Raw PCM concatenation is byte-safe (no frame headers).
 */
export const pcmChunksToMp3 = (
  chunks: Buffer[],
  outPath: string
): Promise<void> => {
  const combined = Buffer.concat(chunks);
  return pcmToMp3(combined, outPath);
};

/**
 * Concatenate MP3 files with 200ms silence between each.
 * Uses ffmpeg concat demuxer — safe for MP3 (unlike raw Buffer.concat).
 */
export const concatMp3Files = (
  inputPaths: string[],
  outPath: string
): Promise<void> => {
  return new Promise((resolve, reject) => {
    if (inputPaths.length === 0) {
      return reject(new Error('No MP3 files to concatenate'));
    }
    if (inputPaths.length === 1) {
      fs.copyFileSync(inputPaths[0], outPath);
      return resolve();
    }

    const silencePath = path.join(os.tmpdir(), `silence_${uuidv4()}.mp3`);
    const listFile = path.join(os.tmpdir(), `concat_${uuidv4()}.txt`);

    // Step 1: generate 200ms silence MP3
    ffmpeg()
      .input('aevalsrc=0')
      .inputOption('-f lavfi')
      .audioFrequency(24000)
      .audioChannels(1)
      .duration(0.2)
      .toFormat('mp3')
      .on('error', reject)
      .on('end', () => {
        // Step 2: build interleaved list [track, silence, track, ...]
        const entries: string[] = [];
        inputPaths.forEach((p, i) => {
          entries.push(`file '${p}'`);
          if (i < inputPaths.length - 1) {
            entries.push(`file '${silencePath}'`);
          }
        });
        fs.writeFileSync(listFile, entries.join('\n'));

        // Step 3: concat all
        ffmpeg(listFile)
          .inputOption('-f concat')
          .inputOption('-safe 0')
          .outputOption('-c copy')
          .on('error', (err) => {
            fs.unlink(listFile, () => undefined);
            fs.unlink(silencePath, () => undefined);
            reject(err);
          })
          .on('end', () => {
            fs.unlink(listFile, () => undefined);
            fs.unlink(silencePath, () => undefined);
            resolve();
          })
          .save(outPath);
      })
      .save(silencePath);
  });
};

/**
 * Get MP3 duration in seconds.
 * music-metadata v10+ is ESM-only. We use Function() to prevent TypeScript
 * from compiling import() → require(), which would fail for ESM packages.
 */
export const getMp3DurationSeconds = async (
  filePath: string
): Promise<number | null> => {
  try {
    const mod = (await new Function('s', 'return import(s)')(
      'music-metadata'
    )) as typeof import('music-metadata');
    const metadata = await mod.parseFile(filePath);
    return metadata.format.duration ?? null;
  } catch (err) {
    logger.warn('Could not read MP3 duration', { filePath, err });
    return null;
  }
};
