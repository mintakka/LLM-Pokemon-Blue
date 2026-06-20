-- Simple test script for mGBA

-- Create a debug buffer
debugBuffer = console:createBuffer("Debug")
debugBuffer:setSize(100, 50)
debugBuffer:clear()
debugBuffer:print("Simple test script loaded!\n")

-- Set up socket for communication
statusSocket = nil

-- Screenshot variables
lastScreenshotTime = 0
screenshotInterval = 3  -- seconds

-- Function to take screenshots and send to the controller
function captureAndSendScreenshot()
    local currentTime = os.time()
    
    -- Only capture screenshots every N seconds
    if currentTime - lastScreenshotTime >= screenshotInterval then
        debugBuffer:print("Taking screenshot...\n")
        
        -- Take screenshot and save to file
        -- Make sure path exists and is writable
        local screenshotPath = "/Users/matt/Projects/LLM-Pokemon-Blue/data/screenshots/screenshot.png"
        emu:screenshot(screenshotPath)
        
        -- Send message to controller if socket is connected
        if statusSocket then
            statusSocket:send("screenshot||" .. screenshotPath .. "\n")
            debugBuffer:print("Sent screenshot notification\n")
        else
            debugBuffer:print("Socket not connected\n")
        end
        
        -- Update timestamp
        lastScreenshotTime = currentTime
        debugBuffer:print("Screenshot time updated to " .. currentTime .. "\n")
    end
end

-- Socket functions
function startSocket()
    debugBuffer:print("Connecting to Python controller...\n")
    statusSocket = socket.tcp()
    
    if not statusSocket then
        debugBuffer:print("Failed to create socket\n")
        return
    end
    
    -- Add callbacks
    statusSocket:add("received", socketReceived)
    statusSocket:add("error", socketError)
    
    -- Connect to the controller
    if statusSocket:connect("127.0.0.1", 8888) then
        debugBuffer:print("Successfully connected to controller\n")
    else
        debugBuffer:print("Failed to connect to controller\n")
        stopSocket()
    end
end

function socketReceived()
    while true do
        local data, err = statusSocket:receive(1024)
        if data then
            debugBuffer:print("Received: " .. data .. "\n")
            
            -- Convert to key press if it's a number
            local keyIndex = tonumber(data)
            if keyIndex and keyIndex >= 0 and keyIndex <= 9 then
                local keyNames = { "A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L" }
                debugBuffer:print("Pressing key: " .. keyNames[keyIndex + 1] .. "\n")
                emu:clearKeys(0x3FF)  -- Clear all keys
                emu:addKey(keyIndex)  -- Press the received key
            end
        else
            if err ~= socket.ERRORS.AGAIN then
                debugBuffer:print("Socket receive error: " .. err .. "\n")
                stopSocket()
            end
            return
        end
    end
end

function socketError(err)
    debugBuffer:print("Socket error: " .. err .. "\n")
    stopSocket()
end

function stopSocket()
    if statusSocket then
        statusSocket:close()
        statusSocket = nil
        debugBuffer:print("Socket closed\n")
    end
end

-- Add callbacks
callbacks:add("frame", captureAndSendScreenshot)
callbacks:add("start", startSocket)

-- Output some debug info
debugBuffer:print("Script initialized\n")
debugBuffer:print("Screenshot interval: " .. screenshotInterval .. " seconds\n")
debugBuffer:print("Current time: " .. os.time() .. "\n")

-- Start socket connection
startSocket()
