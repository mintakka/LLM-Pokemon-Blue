-- Pokemon Blue Memory Test Script for mGBA
-- This script reads player position, direction and map data from memory

-- Socket setup for communication with Python controller
statusSocket = nil
lastUpdateTime = 0
updateInterval = 1  -- Send updates every second

-- Memory addresses for Pokemon Blue (Game Boy)
local memoryAddresses = {
    playerDirection = 0xC109,  -- Direction facing (0:Down, 4:Up, 8:Left, 12:Right)
    playerX = 0xD362,          -- X coordinate on map
    playerY = 0xD361,          -- Y coordinate on map
    mapId = 0xD35E,            -- Current map ID
    -- Add more addresses as we discover them
}

-- Debug buffer setup
function setupBuffer()
    debugBuffer = console:createBuffer("Pokemon Memory Debug")
    debugBuffer:setSize(100, 40)
    debugBuffer:clear()
    debugBuffer:print("Pokemon Memory Test Script initialized\n")
end

-- Direction value to text conversion
function getDirectionText(value)
    if value == 0 then return "DOWN"
    elseif value == 4 then return "UP"
    elseif value == 8 then return "LEFT"
    elseif value == 12 then return "RIGHT"
    else return "UNKNOWN (" .. value .. ")"
    end
end

-- Read and format all memory values
function readGameMemory()
    local memoryData = {}
    
    -- Read direction and convert to readable form
    local directionValue = emu:read8(memoryAddresses.playerDirection)
    memoryData.direction = {
        value = directionValue,
        text = getDirectionText(directionValue)
    }
    
    -- Read coordinates
    memoryData.position = {
        x = emu:read8(memoryAddresses.playerX),
        y = emu:read8(memoryAddresses.playerY)
    }
    
    -- Read map ID
    memoryData.mapId = emu:read8(memoryAddresses.mapId)
    
    return memoryData
end

-- Monitor and send memory values
function monitorMemory()
    local currentTime = os.time()
    
    -- Only send updates at specified interval
    if currentTime - lastUpdateTime >= updateInterval then
        local memoryData = readGameMemory()
        
        -- Display in debug console
        debugBuffer:print("\n--- Memory Values at " .. os.date("%H:%M:%S") .. " ---\n")
        debugBuffer:print("Player Direction: " .. memoryData.direction.text .. " (Value: " .. memoryData.direction.value .. ")\n")
        debugBuffer:print("Player Position: X=" .. memoryData.position.x .. ", Y=" .. memoryData.position.y .. "\n")
        debugBuffer:print("Map ID: " .. memoryData.mapId .. "\n")
        
        -- Send to Python if socket connected
        if statusSocket then
            local jsonData = "{" ..
                "\"direction\":{\"value\":" .. memoryData.direction.value .. 
                ",\"text\":\"" .. memoryData.direction.text .. "\"}," ..
                "\"position\":{\"x\":" .. memoryData.position.x .. 
                ",\"y\":" .. memoryData.position.y .. "}," ..
                "\"mapId\":" .. memoryData.mapId ..
                "}"
                
            sendMessage("memory_data", jsonData)
        end
        
        -- Update last update time
        lastUpdateTime = currentTime
    end
end

-- Socket management functions
function sendMessage(messageType, content)
    if statusSocket then
        statusSocket:send(messageType .. "||" .. content .. "\n")
    end
end

function socketReceived()
    local data, err = statusSocket:receive(1024)
    
    if data then
        debugBuffer:print("Received from controller: '" .. data .. "'\n")
    elseif err ~= socket.ERRORS.AGAIN then
        debugBuffer:print("Socket error: " .. err .. "\n")
        stopSocket()
    end
end

function socketError(err)
    debugBuffer:print("Socket error: " .. err .. "\n")
    stopSocket()
end

function stopSocket()
    if not statusSocket then return end
    debugBuffer:print("Closing socket connection\n")
    statusSocket:close()
    statusSocket = nil
end

function startSocket()
    debugBuffer:print("Connecting to test controller at 127.0.0.1:8889...\n")
    statusSocket = socket.tcp()
    
    if not statusSocket then
        debugBuffer:print("Failed to create socket\n")
        return
    end
    
    -- Add callbacks
    statusSocket:add("received", socketReceived)
    statusSocket:add("error", socketError)
    
    -- Connect to the controller
    if statusSocket:connect("127.0.0.1", 8889) then
        debugBuffer:print("Successfully connected to controller\n")
    else
        debugBuffer:print("Failed to connect to controller\n")
        stopSocket()
    end
end

-- Add callbacks
callbacks:add("start", setupBuffer)
callbacks:add("start", startSocket)
callbacks:add("frame", monitorMemory)

-- Initialize on script load
if emu then
    setupBuffer()
    startSocket()
    debugBuffer:print("Memory test script loaded.\nWaiting for game data...\n")
end
