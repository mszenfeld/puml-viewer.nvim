local M = {}

local state = {
  job_id = nil,
  port = nil,
  token = nil,
}

--- Get the path to server.py relative to this plugin.
---@return string
local function get_server_script_path()
  -- Resolve from the plugin's runtime path
  local source = debug.getinfo(1, "S").source:sub(2) -- remove leading @
  local plugin_root = vim.fn.fnamemodify(source, ":h:h:h")
  return plugin_root .. "/server/server.py"
end

--- Start the preview server process asynchronously.
--- The on_ready callback is invoked with the port once the server reports it.
---@param config table Plugin configuration
---@param on_ready fun(port: number)|nil Callback invoked with the port when the server is ready
function M.start(config, on_ready)
  if state.job_id then
    if on_ready then
      on_ready(state.port)
    end
    return
  end

  local script_path = get_server_script_path()

  if vim.fn.filereadable(script_path) == 0 then
    vim.notify("puml-viewer: server.py not found at " .. script_path, vim.log.levels.ERROR)
    return
  end

  -- When plantuml_cmd is a table, join with shell quoting so that
  -- Python's shlex.split() can reconstruct the original arguments.
  local plantuml_cmd_str
  if type(config.plantuml_cmd) == "table" then
    local parts = {}
    for _, part in ipairs(config.plantuml_cmd) do
      if part:find("[%s\"'\\]") then
        -- Shell-quote arguments containing special characters
        parts[#parts + 1] = "'" .. part:gsub("'", "'\\''") .. "'"
      else
        parts[#parts + 1] = part
      end
    end
    plantuml_cmd_str = table.concat(parts, " ")
  else
    plantuml_cmd_str = config.plantuml_cmd
  end

  local cmd = {
    "python3",
    script_path,
    "--plantuml-cmd",
    plantuml_cmd_str,
  }

  if config.server_port ~= 0 then
    table.insert(cmd, "--port")
    table.insert(cmd, tostring(config.server_port))
  end

  local timeout_timer = nil
  local notified = false

  local job_id = vim.fn.jobstart(cmd, {
    stdin = "pipe",
    on_stdout = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          local ok, parsed = pcall(vim.fn.json_decode, line)
          if ok and parsed and parsed.port and not notified then
            state.port = parsed.port
            state.token = parsed.token
            notified = true
            if timeout_timer then
              vim.fn.timer_stop(timeout_timer)
              timeout_timer = nil
            end
            if on_ready then
              vim.schedule(function()
                on_ready(state.port)
              end)
            end
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
      state.token = nil
      if timeout_timer then
        vim.fn.timer_stop(timeout_timer)
        timeout_timer = nil
      end
      if exit_code ~= 0 and exit_code ~= 143 then -- 143 = SIGTERM
        vim.notify("puml-viewer server exited with code " .. exit_code, vim.log.levels.WARN)
      end
    end,
  })

  if job_id <= 0 then
    vim.notify("puml-viewer: failed to start server", vim.log.levels.ERROR)
    return
  end

  state.job_id = job_id

  -- Set a timeout so we don't wait forever if the server never reports its port
  timeout_timer = vim.fn.timer_start(5000, function()
    if not notified then
      vim.schedule(function()
        vim.notify("puml-viewer: server did not report port in time", vim.log.levels.ERROR)
        M.stop()
      end)
    end
  end)
end

--- Stop the preview server.
function M.stop()
  if state.job_id then
    vim.fn.jobstop(state.job_id)
    state.job_id = nil
    state.port = nil
    state.token = nil
  end
end

--- Get the current server port.
---@return number|nil
function M.get_port()
  return state.port
end

--- Get the current session token.
---@return string|nil
function M.get_token()
  return state.token
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

  local ok = pcall(vim.fn.chansend, state.job_id, msg .. "\n")
  if not ok then
    return false
  end
  return true
end

return M
