-- Token bucket rate limiter (fixed window).
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local current = redis.call('GET', key)
if current and tonumber(current) >= limit then
    return 0
end

redis.call('INCR', key)
redis.call('EXPIRE', key, window)
return 1
