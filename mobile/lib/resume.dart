import 'dart:typed_data';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:pdfx/pdfx.dart';
import 'api.dart';
import 'ui.dart';

/// Load PDFs through the authenticated API; export only on explicit request.
class ResumeViewer extends StatefulWidget {
  final Api api;
  final String path, title;
  const ResumeViewer(
      {super.key,
      required this.api,
      required this.path,
      this.title = 'Currículo PDF'});
  @override
  State<ResumeViewer> createState() => _ResumeViewerState();
}

class _ResumeViewerState extends State<ResumeViewer> {
  PdfControllerPinch? _controller;
  Uint8List? _bytes;
  Object? _error;
  bool _saving = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final bytes = await widget.api.downloadPdf(widget.path);
      if (!mounted) return;
      _bytes = bytes;
      if (!await hasPdfSupport()) {
        throw const ApiException(
            'A visualização de PDF não está disponível neste dispositivo. Você pode baixar uma cópia pelo botão acima.');
      }
      final document = await PdfDocument.openData(bytes);
      if (!mounted) {
        await document.close();
        return;
      }
      setState(() {
        _controller = PdfControllerPinch(document: Future.value(document));
      });
    } catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  Future<void> _save() async {
    if (_bytes == null || _saving) return;
    setState(() => _saving = true);
    try {
      await FilePicker.platform.saveFile(
          dialogTitle: 'Salvar currículo PDF',
          fileName: 'curriculo.pdf',
          type: FileType.custom,
          allowedExtensions: ['pdf'],
          bytes: _bytes);
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    _bytes = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.title), actions: [
          IconButton(
              tooltip: 'Baixar currículo PDF',
              onPressed: _bytes == null || _saving ? null : _save,
              icon: const Icon(Icons.download_outlined))
        ]),
        body: _error != null
            ? EmptyState(
                icon: Icons.picture_as_pdf_outlined,
                title: 'Não foi possível abrir o currículo',
                message: _error is ApiException
                    ? (_error as ApiException).message
                    : 'O PDF não pôde ser exibido. Você pode baixar uma cópia pelo botão acima.')
            : _controller == null
                ? const Center(child: CircularProgressIndicator())
                : PdfViewPinch(
                    controller: _controller!,
                    onDocumentError: (error) {
                      if (mounted) setState(() => _error = error);
                    }),
      );
}
