local M = {}

--- Check if the current buffer is a PlantUML file.
---@return boolean
function M.is_plantuml_file()
  return vim.bo.filetype == "plantuml"
end

--- Split a shell command string into a list of arguments, respecting quotes.
--- Handles single quotes, double quotes, and backslash escapes.
--- If the input is already a table, returns a deep copy.
---@param cmd string|table The command to split
---@return string[]
function M.shell_split(cmd)
  if type(cmd) == "table" then
    return vim.deepcopy(cmd)
  end

  local args = {}
  local current = {}
  local in_single_quote = false
  local in_double_quote = false
  local i = 1
  local len = #cmd

  while i <= len do
    local c = cmd:sub(i, i)

    if in_single_quote then
      if c == "'" then
        in_single_quote = false
      else
        table.insert(current, c)
      end
    elseif in_double_quote then
      if c == "\\" and i < len then
        local next_c = cmd:sub(i + 1, i + 1)
        if next_c == '"' or next_c == "\\" then
          table.insert(current, next_c)
          i = i + 1
        else
          table.insert(current, c)
        end
      elseif c == '"' then
        in_double_quote = false
      else
        table.insert(current, c)
      end
    else
      if c == "\\" and i < len then
        table.insert(current, cmd:sub(i + 1, i + 1))
        i = i + 1
      elseif c == "'" then
        in_single_quote = true
      elseif c == '"' then
        in_double_quote = true
      elseif c == " " or c == "\t" then
        if #current > 0 then
          table.insert(args, table.concat(current))
          current = {}
        end
      else
        table.insert(current, c)
      end
    end

    i = i + 1
  end

  if #current > 0 then
    table.insert(args, table.concat(current))
  end

  return args
end

return M
