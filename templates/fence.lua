-- docx -> Markdown: emit code as fenced blocks (Word keeps no fence or language, so pandoc writes
-- indented blocks). Restores "python" when the block plainly is Python; otherwise leaves the fence bare.
function CodeBlock(b)
  local lang = b.classes[1] or ""
  if lang == "" then
    local t = b.text
    if t:match("^%s*from [%w_.]+ import") or t:match("^%s*import [%w_.]+")
       or t:match("^%s*class %w+") or t:match("^%s*def %w+") then
      lang = "python"
    end
  end
  local fence = "```"
  while b.text:find(fence, 1, true) do fence = fence .. "`" end
  return pandoc.RawBlock("markdown", fence .. lang .. "\n" .. b.text .. "\n" .. fence)
end
