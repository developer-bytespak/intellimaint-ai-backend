import Redis from "ioredis";
import { appConfig } from "src/config/app.config";
if (!appConfig.redisUrl) {
    throw new Error("Redis URL is not defined in the configuration.");
}

let redis: Redis;


redis = new Redis(appConfig.redisUrl, {
    retryStrategy: (times) => {
        if (times > 3) {
            console.error('Redis connection failed after 3 attempts.');
            return null;
        }
        return 2000; // retry after 2 seconds
    },
    maxRetriesPerRequest: null,
    enableOfflineQueue: true,
    enableReadyCheck: true,
});

// Handle connection errors
redis.on('error', (err) => {
    console.error('Redis connection error:', err.message);
    // Don't let unhandled errors crash the app
});

redis.on('connect', () => {
    console.log('Redis connected successfully');
});

redis.on('ready', () => {
    console.log('Redis is ready to accept commands');
});

redis.on('close', () => {
    console.log('Redis connection closed');
});

export { redis };

//* ✅ SAFE SET FOR OTP
export async function safeSet(
    key: string,
    value: string,
    ttlSeconds: number
): Promise<{ success: boolean; error?: any }> {
    console.log("key ==>", key)
    console.log("value ==>", value)
    console.log("ttlSeconds ==>", ttlSeconds)
    try {
        await redis.set(key, value, "EX", ttlSeconds);
        return { success: true };
    } catch (err) {
        console.error(`Redis SET failed for key: ${key}`, err);
        return { success: false, error: err || "Redis set failed" };
    }
}

//* SAFE GET FOR OTP

export async function safeGet(
    key: string
): Promise<unknown | null> {
    try {
        // console.log("key ==>", key)
        const data = await redis.get(key);

        console.log("data ==>", data);
        if (!data) return null;
        // Try to parse as JSON, if fails return as string
        try {
            return JSON.parse(data) as unknown;
        } catch {
            return data;
        }
    } catch (error) {
        console.log(`Redis Get failed for key: ${key}`, error)
        return null;
    }
}

//* DELETE REDISKEY :

export async function redisDeleteKey(
    key: string
): Promise<boolean> {
    try {
        await redis.del(key);
        return true
    } catch (error) {
        console.log(`Redis Get failed for key: ${key}`, error)
        return false;
    }
}


export async function getOrSetCache<T>(
    key: string,
    ttl: number,
    fetcher: () => Promise<T>,
): Promise<T> {
    const cachedData = await redis.get(key);
    if (cachedData) {
        return JSON.parse(cachedData) as T;
    }

    const data = await fetcher();
    await redis.set(key, JSON.stringify(data), "EX", ttl);
    return data;
}

export async function clearCache(keys: string[]): Promise<void> {
    if (keys.length === 0) return;
    await redis.del(keys);
}