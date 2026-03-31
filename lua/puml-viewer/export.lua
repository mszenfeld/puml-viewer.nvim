local utils = require("puml-viewer.utils")

local M = {}

--- Get the output path for an exported diagram.
---@param format string "png" or "svg"
---@param export_dir string|nil Optional export directory
---@return string
function M.get_export_path(format, export_dir)
  local filename = vim.fn.expand("%:p")
  local basename = vim.fn.fnamemodify(filename, ":t:r")
  local dir = export_dir or vim.fn.fnamemodify(filename, ":h")
  return dir .. "/" .. basename .. "." .. format
end

--- Export the current buffer to PNG or SVG.
---@param format string "png" or "svg"
---@param config table Plugin configuration
function M.export(format, config)
  if not utils.is_plantuml_file() then
    vim.notify("puml-viewer: not a PlantUML file", vim.log.levels.WARN)
    return
  end

  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  local content = table.concat(lines, "\n")

  if content:match("^%s*$") then
    vim.notify("puml-viewer: buffer is empty", vim.log.levels.INFO)
    return
  end

  -- Write content to a temp file with same basename so plantuml output matches
  local source_basename = vim.fn.expand("%:t:r")
  local temp_dir = vim.fn.tempname()
  vim.fn.mkdir(temp_dir, "p")
  local temp_file = temp_dir .. "/" .. source_basename .. ".puml"

  local file = io.open(temp_file, "w")
  if not file then
    vim.notify("puml-viewer: failed to create temp file", vim.log.levels.ERROR)
    return
  end
  file:write(content)
  file:close()

  -- Determine output directory
  local output_dir = config.export_dir or vim.fn.fnamemodify(vim.fn.expand("%:p"), ":h")
  local expected_output = output_dir .. "/" .. source_basename .. "." .. format

  -- Build plantuml command (supports both string and table forms,
  -- with proper shell quoting for paths with spaces)
  local cmd = utils.shell_split(config.plantuml_cmd)
  vim.list_extend(cmd, { "-t" .. format, "-o", output_dir, temp_file })

  vim.fn.jobstart(cmd, {
    on_exit = function(_, exit_code)
      -- Clean up temp files
      os.remove(temp_file)
      vim.fn.delete(temp_dir, "rf")

      if exit_code == 0 then
        vim.schedule(function()
          vim.notify("puml-viewer: exported to " .. expected_output, vim.log.levels.INFO)
        end)
      else
        vim.schedule(function()
          vim.notify("puml-viewer: export failed (exit code " .. exit_code .. ")", vim.log.levels.ERROR)
        end)
      end
    end,
    on_stderr = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          vim.schedule(function()
            vim.notify("puml-viewer: " .. line, vim.log.levels.WARN)
          end)
        end
      end
    end,
  })
end

return M
