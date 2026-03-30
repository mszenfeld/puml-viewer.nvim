local M = {}

local state = {
  job_id = nil,
  port = nil,
}

--- Get the path to server.py relative to this plugin.
---@return string
local function get_server_script_path()
  -- Resolve from the plugin's runtime path
  local source = debug.getinfo(1, "S").source:sub(2) -- remove leading @
  local plugin_root = vim.fn.fnamemodify(source, ":h:h:h")
  return plugin_root .. "/server/server.py"
end

--- Start the preview server process.
---@param config table Plugin configuration
---@return number|nil port The port the server is listening on, or nil on failure
function M.start(config)
  if state.job_id then
    return state.port
  end

  local script_path = get_server_script_path()

  if vim.fn.filereadable(script_path) == 0 then
    vim.notify("puml-viewer: server.py not found at " .. script_path, vim.log.levels.ERROR)
    return nil
  end

  local cmd = {
    "python3",
    script_path,
    "--plantuml-cmd",
    config.plantuml_cmd,
  }

  if config.server_port ~= 0 then
    table.insert(cmd, "--port")
    table.insert(cmd, tostring(config.server_port))
  end

  local port_received = false

  local job_id = vim.fn.jobstart(cmd, {
    stdin = "pipe",
    on_stdout = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          local ok, parsed = pcall(vim.fn.json_decode, line)
          if ok and parsed and parsed.port then
            state.port = parsed.port
            port_received = true
          end
        end
      end
    end,
    on_stderr = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          vim.notify("puml-viewer server: " .. line, vim.log.levels.WARN)
        end
      end
    end,
    on_exit = function(_, exit_code)
      state.job_id = nil
      state.port = nil
      if exit_code ~= 0 and exit_code ~= 143 then -- 143 = SIGTERM
        vim.notify("puml-viewer server exited with code " .. exit_code, vim.log.levels.WARN)
      end
    end,
  })

  if job_id <= 0 then
    vim.notify("puml-viewer: failed to start server", vim.log.levels.ERROR)
    return nil
  end

  state.job_id = job_id

  -- Wait for the port to be received (up to 2s)
  vim.wait(2000, function()
    return port_received
  end, 50)

  if not port_received then
    vim.notify("puml-viewer: server did not report port in time", vim.log.levels.ERROR)
    M.stop()
    return nil
  end

  return state.port
end

--- Stop the preview server.
function M.stop()
  if state.job_id then
    vim.fn.jobstop(state.job_id)
    state.job_id = nil
    state.port = nil
  end
end

--- Get the current server port.
---@return number|nil
function M.get_port()
  return state.port
end

--- Check if the server is running.
---@return boolean
function M.is_running()
  return state.job_id ~= nil
end

--- Send a buffer update to the server.
---@param content string The PlantUML source content
---@return boolean success
function M.send_update(content)
  if not state.job_id then
    return false
  end

  local msg = vim.fn.json_encode({
    type = "update",
    content = content,
  })

  vim.fn.chansend(state.job_id, msg .. "\n")
  return true
end

return M
