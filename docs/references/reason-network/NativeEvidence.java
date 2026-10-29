// Reason 바이너리 복사본에서 주소·문자열 참조·선택 함수 디컴파일 근거를 수집한다.
// @category XSM.Research
import ghidra.app.util.headless.HeadlessScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;
import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

public class NativeEvidence extends HeadlessScript {
    private final LinkedHashMap<String, Function> chosen = new LinkedHashMap<>();
    private int limit = 12;

    private void choose(Function f) {
        if (f != null && !f.isExternal() && chosen.size() < limit)
            chosen.putIfAbsent(f.getEntryPoint().toString(), f);
    }

    private Map<String, Object> functionInfo(Function f) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("address", f.getEntryPoint().toString());
        row.put("name", f.getName(true));
        row.put("body_addresses", f.getBody().getNumAddresses());
        row.put("thunk", f.isThunk());
        ArrayList<String> calls = new ArrayList<>();
        for (Function callee : f.getCalledFunctions(monitor)) {
            if (calls.size() >= 24) break;
            calls.add(callee.getEntryPoint() + " " + callee.getName(true));
        }
        row.put("callees_first_24", calls);
        return row;
    }

    private String sha(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2 || currentProgram == null)
            throw new IllegalArgumentException("output directory and layout JSON required");
        Path output = Paths.get(args[0]);
        Files.createDirectories(output);
        JsonObject layout = JsonParser.parseString(Files.readString(Paths.get(args[1]))).getAsJsonObject();
        if (args.length > 2) limit = Integer.parseInt(args[2]);
        Map<String, Object> result = new LinkedHashMap<>();
        Memory memory = currentProgram.getMemory();
        result.put("program", currentProgram.getName());
        result.put("executable_format", currentProgram.getExecutableFormat());
        result.put("language", currentProgram.getLanguageID().toString());
        result.put("compiler_spec", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        result.put("image_base", currentProgram.getImageBase().toString());
        result.put("function_count", currentProgram.getFunctionManager().getFunctionCount());
        if (layout.has("retained_analysis_only") && layout.get("retained_analysis_only").getAsBoolean()) {
            result.put("analysis_timed_out", layout.get("prior_auto_analysis_timed_out").getAsBoolean());
            result.put("analysis_scope", "retained project export; timeout flag belongs to the prior automatic analysis");
        } else {
            result.put("analysis_timed_out", analysisTimeoutOccurred());
            result.put("analysis_scope", "automatic analysis in this run");
        }
        result.put("target_sha256", sha(Files.readAllBytes(Paths.get(currentProgram.getExecutablePath()))));

        ArrayList<Map<String, Object>> blocks = new ArrayList<>();
        for (MemoryBlock block : memory.getBlocks()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", block.getName()); row.put("start", block.getStart().toString());
            row.put("end", block.getEnd().toString()); row.put("size", block.getSize());
            row.put("initialized", block.isInitialized()); row.put("execute", block.isExecute());
            row.put("write", block.isWrite()); blocks.add(row);
        }
        result.put("memory_blocks", blocks);

        if (layout.has("entry_address") && !layout.get("entry_address").isJsonNull()) {
            Address entry = toAddr(layout.get("entry_address").getAsString());
            choose(getFunctionContaining(entry));
        }
        ArrayList<Map<String, Object>> entries = new ArrayList<>();
        AddressIterator iterator = currentProgram.getSymbolTable().getExternalEntryPointIterator();
        while (iterator.hasNext() && entries.size() < 16) {
            Address address = iterator.next(); Function f = getFunctionContaining(address);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("address", address.toString()); row.put("function", f == null ? null : f.getName(true));
            entries.add(row);
        }
        result.put("entry_points", entries);

        ArrayList<Map<String, Object>> recovered = new ArrayList<>();
        if (layout.has("recover_entry_calls") && layout.has("entry_address")) {
            HashSet<String> wanted = new HashSet<>();
            for (JsonElement e : layout.getAsJsonArray("recover_entry_calls")) wanted.add(toAddr(e.getAsString()).toString());
            Function entryFunction = getFunctionContaining(toAddr(layout.get("entry_address").getAsString()));
            if (entryFunction != null) {
                ArrayList<Address> calls = new ArrayList<>();
                ArrayList<Address> sources = new ArrayList<>();
                InstructionIterator instructions = currentProgram.getListing().getInstructions(entryFunction.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    if (!instruction.getFlowType().isCall()) continue;
                    for (Address target : instruction.getFlows()) {
                        if (wanted.contains(target.toString())) { calls.add(target); sources.add(instruction.getAddress()); }
                    }
                }
                for (int i = 0; i < calls.size(); i++) {
                    Address target = calls.get(i); MemoryBlock block = memory.getBlock(target);
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("target", target.toString()); row.put("call_instruction", sources.get(i).toString());
                    Function function = getFunctionAt(target); boolean created = false;
                    if (function == null && block != null && block.isExecute()) {
                        disassemble(target);
                        function = createFunction(target, "native_call_target_" + target.toString());
                        created = function != null;
                    }
                    row.put("created_in_analysis_project", created);
                    row.put("function", function == null ? null : function.getName(true));
                    recovered.add(row); choose(function); wanted.remove(target.toString());
                }
            }
            result.put("unmatched_recovery_requests", wanted);
        }
        result.put("script_recovered_entry_call_targets", recovered);

        ArrayList<Map<String, Object>> linkerRecovered = new ArrayList<>();
        if (layout.has("recover_linker_functions")) {
            for (JsonElement e : layout.getAsJsonArray("recover_linker_functions")) {
                JsonObject candidate = e.getAsJsonObject();
                Address start = toAddr(candidate.get("start").getAsString());
                Address evidence = toAddr(candidate.get("evidence_address").getAsString());
                MemoryBlock block = memory.getBlock(start);
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("start", start.toString()); row.put("evidence_address", evidence.toString());
                row.put("needle", candidate.get("needle").getAsString());
                row.put("next_linker_start", candidate.get("next_start").getAsString());
                row.put("boundary_source", "LC_FUNCTION_STARTS in the target Mach-O");
                Function function = getFunctionAt(start); boolean created = false;
                if (function == null && getFunctionContaining(start) == null && block != null && block.isExecute()) {
                    disassemble(start);
                    if (currentProgram.getListing().getInstructionAt(evidence) != null) {
                        function = createFunction(start, "linker_function_" + start.toString());
                        created = function != null;
                    }
                }
                boolean contains = function != null && function.getBody().contains(evidence);
                row.put("created_in_analysis_project", created); row.put("contains_evidence_instruction", contains);
                row.put("function", function == null ? null : function.getName(true));
                linkerRecovered.add(row); if (contains) choose(function);
            }
        }
        result.put("script_recovered_linker_functions", linkerRecovered);

        ArrayList<Map<String, Object>> regions = new ArrayList<>();
        for (JsonElement element : layout.getAsJsonArray("javascript_regions")) {
            JsonObject region = element.getAsJsonObject();
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", region.get("name").getAsString());
            row.put("file_offset", region.get("file_offset").getAsLong());
            if (!region.get("address").isJsonNull()) {
                Address address = toAddr(region.get("address").getAsString());
                row.put("address", address.toString());
                MemoryBlock block = memory.getBlock(address);
                row.put("block", block == null ? null : block.getName());
                row.put("execute", block != null && block.isExecute());
                Function f = getFunctionContaining(address);
                row.put("native_function_at_start", f == null ? null : f.getName(true));
                byte[] bytes = new byte[region.get("bytes").getAsInt()];
                int read = memory.getBytes(address, bytes);
                row.put("bytes_read", read); row.put("sha256", sha(bytes));
                row.put("matches_extracted_module", read == bytes.length && sha(bytes).equals(region.get("sha256").getAsString()));
            } else row.put("address", null);
            regions.add(row);
        }
        result.put("javascript_regions", regions);

        String[] needles = layout.has("needles")
            ? new Gson().fromJson(layout.get("needles"), String[].class)
            : new String[]{"codex", "--thread", "falling back to hooks", "not a member of this team", "CODEX_HOME"};
        ArrayList<Map<String, Object>> matches = new ArrayList<>();
        for (String needle : needles) {
            int hits = 0;
            byte[] bytes = needle.getBytes(StandardCharsets.UTF_8);
            for (MemoryBlock block : memory.getBlocks()) {
                if (!block.isInitialized() || block.isExecute() || hits >= 6) continue;
                Address from = block.getStart();
                while (from.compareTo(block.getEnd()) <= 0 && hits < 6 && !monitor.isCancelled()) {
                    Address found = memory.findBytes(from, block.getEnd(), bytes, null, true, monitor);
                    if (found == null) break;
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("needle", needle); row.put("address", found.toString());
                    row.put("block", block.getName());
                    ArrayList<Map<String, Object>> refs = new ArrayList<>();
                    ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(found);
                    while (references.hasNext() && refs.size() < 24) {
                        Reference ref = references.next();
                        Function f = getFunctionContaining(ref.getFromAddress());
                        Map<String, Object> r = new LinkedHashMap<>();
                        r.put("from", ref.getFromAddress().toString()); r.put("type", ref.getReferenceType().toString());
                        r.put("function", f == null ? null : f.getName(true));
                        r.put("function_address", f == null ? null : f.getEntryPoint().toString());
                        refs.add(r); choose(f);
                        if (f == null && refs.size() < 24) {
                            ReferenceIterator indirect = currentProgram.getReferenceManager().getReferencesTo(ref.getFromAddress());
                            while (indirect.hasNext() && refs.size() < 24) {
                                Reference hop = indirect.next();
                                Function caller = getFunctionContaining(hop.getFromAddress());
                                if (caller == null) continue;
                                Map<String, Object> h = new LinkedHashMap<>();
                                h.put("from", hop.getFromAddress().toString());
                                h.put("via_data_reference", ref.getFromAddress().toString());
                                h.put("type", hop.getReferenceType().toString());
                                h.put("function", caller.getName(true));
                                h.put("function_address", caller.getEntryPoint().toString());
                                refs.add(h); choose(caller);
                            }
                        }
                    }
                    row.put("references_first_24", refs); matches.add(row); hits++;
                    if (found.equals(block.getEnd())) break;
                    from = found.add(1);
                }
            }
        }
        result.put("string_matches", matches);
        result.put("string_scope", "initialized non-executable blocks; at most six exact occurrences per needle and 24 refs per occurrence; one data-reference hop is explicitly marked");

        ArrayList<Function> roots = new ArrayList<>(chosen.values());
        for (Function root : roots) {
            if (chosen.size() >= limit) break;
            ArrayList<Function> callees = new ArrayList<>(root.getCalledFunctions(monitor));
            callees.sort(Comparator.comparing(f -> f.getEntryPoint().toString()));
            for (Function callee : callees) choose(callee);
        }

        DecompInterface decompiler = new DecompInterface();
        ArrayList<Map<String, Object>> functions = new ArrayList<>();
        try {
            boolean available = decompiler.openProgram(currentProgram);
            result.put("decompiler_available", available);
            result.put("decompiler_error", available ? null : decompiler.getLastMessage());
            for (Function f : chosen.values()) {
                Map<String, Object> row = functionInfo(f);
                if (!available) {
                    row.put("decompile_completed", false);
                    row.put("error", decompiler.getLastMessage());
                    functions.add(row);
                    continue;
                }
                DecompileResults d = decompiler.decompileFunction(f, 30, monitor);
                row.put("decompile_completed", d.decompileCompleted());
                row.put("error", d.getErrorMessage());
                if (d.decompileCompleted() && d.getDecompiledFunction() != null) {
                    String code = d.getDecompiledFunction().getC();
                    Path file = output.resolve("function-" + f.getEntryPoint().toString().replace(':', '_') + ".c.txt");
                    Files.writeString(file, code); row.put("private_pseudocode_file", file.getFileName().toString());
                    row.put("pseudocode_sha256", sha(code.getBytes(StandardCharsets.UTF_8)));
                    row.put("pseudocode_chars", code.length());
                }
                functions.add(row);
            }
        } finally { decompiler.dispose(); }
        result.put("selected_functions", functions);
        result.put("function_count_after_script", currentProgram.getFunctionManager().getFunctionCount());
        result.put("decompile_scope", "bounded selected native functions; pseudocode is an analysis result, not recovered original source");
        Path file = output.resolve("native-evidence.json");
        Files.writeString(file, new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result) + "\n");
        println("NATIVE_EVIDENCE " + currentProgram.getName() + " functions=" + functions.size() + " strings=" + matches.size() + " output=" + file);
    }
}
